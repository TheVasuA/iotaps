"""Alert_Checker worker (Req 10.2, 10.3, 10.4, 5.7, 30.1).

The Alert_Checker is the Rule_Engine's execution engine. It evaluates each
organization's enabled rule chains against incoming telemetry and runs the
chain's actions (publish command / notify / webhook) when the trigger and every
preceding condition hold (design "Rule Engine Execution Flow" and "Rule Engine
Chain Evaluation").

Design pseudocode (design.md "Rule Engine Chain Evaluation (Req 10.1-10.4)")::

    def evaluate(rule, telemetry, device):
        if device.maintenance_mode: return                 # Req 5.7
        node = rule.trigger_node
        if not trigger_matches(node, telemetry): return
        node = next_node(rule, node)
        while node:
            if node.type == 'condition':
                if not condition_true(node, telemetry): return
            elif node.type == 'delay':
                schedule_continuation(rule, next_node(rule,node), node.duration); return
            elif node.type == 'action':
                execute_action(node, device)               # publish cmd/notify/webhook
            node = next_node(rule, node)

This module splits that flow into a **pure planning core** and an **async
executor** so the whole of Property 17 can be unit/property-tested without any
live broker, Redis, or database:

- :func:`build_chain` orders a rule's ``rule_nodes``/``rule_edges`` graph into
  the linear trigger -> ... chain it represents.
- :func:`plan_chain` walks that chain against one telemetry sample and returns a
  deterministic :class:`ExecutionPlan` of ordered steps (delays + actions). It
  encodes every branch of the design flow: Maintenance_Mode suppresses the whole
  evaluation (Req 5.7); a non-matching trigger or a false condition truncates
  the plan before any action; a delay node defers everything after it.
- :func:`execute_plan` runs a plan against an injected :data:`ActionSink`,
  awaiting an injected ``sleep_fn`` for each delay so "nodes following a delay
  are deferred by at least the delay's duration" is real and testable.

``run``/``main`` wire the pure core to a real telemetry source (Redis pub/sub),
rule/device loaders, and a Redis-backed action sink, mirroring the other workers
(testable pure core + thin run loop with a ``stop_event`` + graceful shutdown).
"""

from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, Optional, Sequence, Union

from app.core import redis_keys as rk
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Node / chain model
# ---------------------------------------------------------------------------
class NodeType(str, Enum):
    """The four rule-node kinds (design "rule_nodes": trigger/condition/action/delay)."""

    TRIGGER = "trigger"
    CONDITION = "condition"
    DELAY = "delay"
    ACTION = "action"


@dataclass(frozen=True)
class RuleNodeSpec:
    """A single rule node decoupled from the ORM (id, type, config)."""

    id: str
    node_type: NodeType
    config: dict[str, Any] = field(default_factory=dict)


def _coerce_node_type(value: Any) -> Optional[NodeType]:
    """Map a stored ``node_type`` string to a :class:`NodeType`, or ``None``."""
    if isinstance(value, NodeType):
        return value
    try:
        return NodeType(str(value).strip().lower())
    except ValueError:
        return None


def build_chain(
    nodes: Iterable[Any],
    edges: Iterable[Any],
) -> list[RuleNodeSpec]:
    """Order a rule's graph into the linear chain starting at its trigger.

    ``nodes`` may be ORM ``RuleNode`` rows or plain objects/dicts exposing
    ``id``, ``node_type`` and ``config``; ``edges`` likewise expose
    ``from_node_id``/``to_node_id`` (ORM) or ``from``/``to`` (dict). The chain is
    built by locating the (single) trigger node and following out-edges until a
    node has no successor, mirroring the trigger -> condition -> delay -> action
    layout the editor produces.

    Returns ``[]`` when there is no trigger node. Cycles are broken by tracking
    visited node ids so a malformed graph can never loop forever.
    """
    specs: dict[str, RuleNodeSpec] = {}
    for node in nodes:
        node_id = _attr(node, "id")
        node_type = _coerce_node_type(_attr(node, "node_type"))
        if node_id is None or node_type is None:
            continue
        config = _attr(node, "config") or {}
        if not isinstance(config, dict):
            config = {}
        specs[str(node_id)] = RuleNodeSpec(str(node_id), node_type, config)

    # Adjacency: from_node_id -> to_node_id (first out-edge wins for a linear chain).
    adjacency: dict[str, str] = {}
    for edge in edges:
        from_id = _attr(edge, "from_node_id", "from")
        to_id = _attr(edge, "to_node_id", "to")
        if from_id is None or to_id is None:
            continue
        adjacency.setdefault(str(from_id), str(to_id))

    trigger = next(
        (s for s in specs.values() if s.node_type is NodeType.TRIGGER), None
    )
    if trigger is None:
        return []

    ordered: list[RuleNodeSpec] = []
    visited: set[str] = set()
    current: Optional[str] = trigger.id
    while current is not None and current in specs and current not in visited:
        visited.add(current)
        ordered.append(specs[current])
        current = adjacency.get(current)
    return ordered


def _attr(obj: Any, *names: str) -> Any:
    """Read the first present attribute/key from ``obj`` (ORM or dict)."""
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif hasattr(obj, name):
            return getattr(obj, name)
    return None


# ---------------------------------------------------------------------------
# Predicate evaluation (triggers + conditions)
# ---------------------------------------------------------------------------
# Comparison operators a trigger/condition node may declare in its config. Both
# the symbolic and word forms are accepted so editor output and hand-written
# graphs both work.
_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "gt": lambda a, b: a > b,
    ">": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    ">=": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "<": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "<=": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "!=": lambda a, b: a != b,
}


def _telemetry_value(telemetry: dict[str, Any], key: str) -> Optional[float]:
    """Return the numeric value for ``key`` in a telemetry sample, or ``None``.

    Accepts either a flat ``{key: value}`` mapping or the wire envelope
    ``{"data": {key: value}}`` (design telemetry contract). Booleans are not
    treated as numbers.
    """
    data = telemetry.get("data") if isinstance(telemetry.get("data"), dict) else telemetry
    value = data.get(key) if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def evaluate_predicate(config: dict[str, Any], telemetry: dict[str, Any]) -> bool:
    """Evaluate a trigger/condition node's predicate against a telemetry sample.

    Config contract (design rule_nodes ``config`` JSONB)::

        {"key": "temp", "op": "gt", "value": 30}

    Rules:
    - With ``op`` + ``value``: the sample's value for ``key`` must compare true
      against ``value``; a missing key, non-numeric value, or unknown operator
      yields ``False``.
    - With a ``key`` but no ``op``: matches when the key is present and numeric
      (a "fires on any reading for this key" trigger).
    - With no ``key``: matches unconditionally (an unguarded trigger).
    """
    key = config.get("key")
    op = config.get("op")

    if key is None:
        return True

    value = _telemetry_value(telemetry, str(key))
    if value is None:
        return False

    if op is None:
        return True

    comparator = _OPERATORS.get(str(op).strip().lower())
    threshold = config.get("value")
    if comparator is None or not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return False
    return comparator(value, float(threshold))


def trigger_matches(node: RuleNodeSpec, telemetry: dict[str, Any]) -> bool:
    """Whether a trigger node fires for ``telemetry`` (design ``trigger_matches``)."""
    return evaluate_predicate(node.config, telemetry)


def condition_true(node: RuleNodeSpec, telemetry: dict[str, Any]) -> bool:
    """Whether a condition node holds for ``telemetry`` (design ``condition_true``)."""
    return evaluate_predicate(node.config, telemetry)


def delay_seconds(node: RuleNodeSpec) -> float:
    """Return a delay node's duration in seconds (non-negative).

    Accepts ``seconds``/``duration``/``delay_seconds`` (seconds) or ``ms``
    (milliseconds). Missing/invalid values default to ``0`` so a malformed delay
    never blocks the chain.
    """
    for key in ("seconds", "duration", "delay_seconds"):
        raw = node.config.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return max(0.0, float(raw))
    ms = node.config.get("ms")
    if isinstance(ms, (int, float)) and not isinstance(ms, bool):
        return max(0.0, float(ms) / 1000.0)
    return 0.0


# ---------------------------------------------------------------------------
# Execution plan (pure result of evaluating a chain)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DelayStep:
    """Defer the rest of the chain by ``seconds`` (a delay node, Req 10.3)."""

    seconds: float


@dataclass(frozen=True)
class ActionStep:
    """Execute one action node's side effect (Req 10.2)."""

    node: RuleNodeSpec


ExecutionStep = Union[DelayStep, ActionStep]


@dataclass(frozen=True)
class ExecutionPlan:
    """The ordered steps to run for one (chain, telemetry) evaluation.

    ``suppressed`` is ``True`` only when evaluation was skipped because the
    device is in Maintenance_Mode (Req 5.7) - distinct from an empty plan caused
    by a non-matching trigger or false condition.
    """

    steps: tuple[ExecutionStep, ...] = ()
    suppressed: bool = False

    @property
    def actions(self) -> list[RuleNodeSpec]:
        """The action nodes that will run, in execution order."""
        return [s.node for s in self.steps if isinstance(s, ActionStep)]

    @property
    def total_delay(self) -> float:
        """Sum of all delay durations before the chain completes."""
        return sum(s.seconds for s in self.steps if isinstance(s, DelayStep))


def plan_chain(
    chain: Sequence[RuleNodeSpec],
    telemetry: dict[str, Any],
    *,
    maintenance_mode: bool,
) -> ExecutionPlan:
    """Walk an ordered chain against one telemetry sample into an execution plan.

    Implements the design ``evaluate`` flow as a pure function (Property 17):

    - ``maintenance_mode`` -> suppressed plan, no steps (Req 5.7).
    - empty chain or a leading non-trigger / non-matching trigger -> empty plan.
    - condition nodes truncate the plan (return what was collected so far) the
      moment one is false, so no later action runs (Req 10.2).
    - a delay node emits a :class:`DelayStep`; everything after it is deferred
      behind that delay (Req 10.3) - the design returns after scheduling a
      continuation, which here is captured as the remaining steps following the
      delay in the plan.
    - action nodes emit an :class:`ActionStep`, preserving chain order.
    """
    if maintenance_mode:
        return ExecutionPlan(suppressed=True)

    if not chain:
        return ExecutionPlan()

    trigger = chain[0]
    if trigger.node_type is not NodeType.TRIGGER:
        return ExecutionPlan()
    if not trigger_matches(trigger, telemetry):
        return ExecutionPlan()

    steps: list[ExecutionStep] = []
    for node in chain[1:]:
        if node.node_type is NodeType.CONDITION:
            if not condition_true(node, telemetry):
                # A false condition stops the chain: no following action runs.
                return ExecutionPlan(steps=tuple(steps))
        elif node.node_type is NodeType.DELAY:
            steps.append(DelayStep(delay_seconds(node)))
        elif node.node_type is NodeType.ACTION:
            steps.append(ActionStep(node))
        # Unknown node types are ignored (forward-compatible with new kinds).
    return ExecutionPlan(steps=tuple(steps))


def evaluate(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    telemetry: dict[str, Any],
    *,
    maintenance_mode: bool,
) -> ExecutionPlan:
    """Build a chain from ``nodes``/``edges`` and plan it for ``telemetry``.

    Convenience wrapper combining :func:`build_chain` and :func:`plan_chain`
    used by the run loop and tests.
    """
    chain = build_chain(nodes, edges)
    return plan_chain(chain, telemetry, maintenance_mode=maintenance_mode)


# ---------------------------------------------------------------------------
# Action model + sink
# ---------------------------------------------------------------------------
class ActionKind(str, Enum):
    """Side effects an action node can request (design "publish cmd/notify/webhook")."""

    COMMAND = "command"
    NOTIFY = "notify"
    WEBHOOK = "webhook"


@dataclass(frozen=True)
class Action:
    """A parsed action: its kind plus the raw action-node config."""

    kind: ActionKind
    config: dict[str, Any]


def parse_action(node: RuleNodeSpec) -> Optional[Action]:
    """Parse an action node's config into an :class:`Action`, or ``None``.

    The kind comes from ``action`` / ``kind`` / ``action_type`` in the config;
    unknown or missing kinds yield ``None`` so a malformed action is skipped
    rather than crashing the worker.
    """
    raw_kind = node.config.get("action") or node.config.get("kind") or node.config.get("action_type")
    if raw_kind is None:
        return None
    try:
        kind = ActionKind(str(raw_kind).strip().lower())
    except ValueError:
        return None
    return Action(kind=kind, config=node.config)


@dataclass(frozen=True)
class TelemetryEvent:
    """One telemetry sample to evaluate rules against."""

    org_id: str
    device_id: str
    data: dict[str, Any]
    rule_id: Optional[str] = None


# An action sink performs one action's side effect for a telemetry event.
ActionSink = Callable[[Action, TelemetryEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# Plan execution (async; injected sink + sleep)
# ---------------------------------------------------------------------------
async def execute_plan(
    plan: ExecutionPlan,
    event: TelemetryEvent,
    sink: ActionSink,
    *,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Execute a plan: await each delay, then dispatch each action to ``sink``.

    Returns the number of actions dispatched. Delays are honoured by awaiting
    ``sleep_fn`` for their duration *before* any subsequent step runs, so the
    nodes following a delay are deferred by at least that duration (Req 10.3,
    Property 17). A suppressed/empty plan dispatches nothing.
    """
    dispatched = 0
    for step in plan.steps:
        if isinstance(step, DelayStep):
            if step.seconds > 0:
                await sleep_fn(step.seconds)
        elif isinstance(step, ActionStep):
            action = parse_action(step.node)
            if action is None:
                logger.warning(
                    "rule_action_unparseable",
                    extra={"node_id": step.node.id, "rule_id": event.rule_id},
                )
                continue
            await sink(action, event)
            dispatched += 1
    return dispatched


# ---------------------------------------------------------------------------
# Default Redis-backed action sink (publish command / notify / webhook)
# ---------------------------------------------------------------------------
# An async callable that publishes a JSON command payload to an MQTT topic,
# used to deliver ``command`` actions to a device (mirrors the command service).
CommandPublisher = Callable[[str, str], Awaitable[None]]


class RedisActionSink:
    """Default :data:`ActionSink` that publishes command/notify/webhook effects.

    - ``command``: published to the device's MQTT command topic when a broker
      ``publisher`` is wired (Req 9.1/9.2 delivery path); otherwise logged.
    - ``notify``: an ``alert`` message is published on the device pub/sub channel
      so the WebSocket gateway and Notification_Sender can surface it (WS
      contract ``{"type":"alert","rule_id":...,"message":...}``).
    - ``webhook``: a ``webhook`` event is published on the device channel for the
      Webhook_Dispatcher (Task 19.2) to deliver.

    Side-effect failures are logged but never raised, so one failing action does
    not abort the rest of the chain or the worker.
    """

    def __init__(self, redis: Any, publisher: Optional[CommandPublisher] = None) -> None:
        self._redis = redis
        self._publisher = publisher

    async def __call__(self, action: Action, event: TelemetryEvent) -> None:
        try:
            if action.kind is ActionKind.COMMAND:
                await self._do_command(action, event)
            elif action.kind is ActionKind.NOTIFY:
                await self._do_notify(action, event)
            elif action.kind is ActionKind.WEBHOOK:
                await self._do_webhook(action, event)
        except Exception:  # pragma: no cover - an action must not crash the loop
            logger.exception(
                "rule_action_failed",
                extra={"kind": action.kind.value, "rule_id": event.rule_id},
            )

    async def _do_command(self, action: Action, event: TelemetryEvent) -> None:
        from app.core.mqtt_topics import command_topic

        body = {
            "type": action.config.get("type", "on"),
        }
        if "value" in action.config:
            body["value"] = action.config["value"]
        payload = json.dumps(body)
        if self._publisher is not None:
            await self._publisher(command_topic(event.org_id, event.device_id), payload)
        else:  # pragma: no cover - no broker wired (e.g. tests / degraded mode)
            logger.info(
                "rule_command_action",
                extra={"device_id": event.device_id, "rule_id": event.rule_id},
            )

    async def _do_notify(self, action: Action, event: TelemetryEvent) -> None:
        message = json.dumps(
            {
                "type": "alert",
                "rule_id": event.rule_id,
                "device_id": event.device_id,
                "title": action.config.get("title"),
                "message": action.config.get("message") or action.config.get("body"),
            }
        )
        await self._redis.publish(rk.device_channel(event.device_id), message)

    async def _do_webhook(self, action: Action, event: TelemetryEvent) -> None:
        message = json.dumps(
            {
                "type": "webhook",
                "rule_id": event.rule_id,
                "device_id": event.device_id,
                "url": action.config.get("url"),
                "payload": action.config.get("payload", event.data),
            }
        )
        await self._redis.publish(rk.device_channel(event.device_id), message)


# ---------------------------------------------------------------------------
# Per-event evaluation (wires loaders + sink for one telemetry sample)
# ---------------------------------------------------------------------------
# A loader returning the enabled rules ((rule_id, nodes, edges)) for an org.
RuleLoader = Callable[[str], Awaitable[Sequence[tuple[str, Sequence[Any], Sequence[Any]]]]]
# A predicate returning whether a device is currently in Maintenance_Mode.
MaintenanceCheck = Callable[[str], Awaitable[bool]]


async def evaluate_event(
    event: TelemetryEvent,
    rules: Sequence[tuple[str, Sequence[Any], Sequence[Any]]],
    *,
    maintenance_mode: bool,
    sink: ActionSink,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Evaluate every rule against one telemetry event and run matching actions.

    Returns the total number of actions dispatched across all rules. When the
    device is in Maintenance_Mode no rule is evaluated and nothing is dispatched
    (Req 5.7). Each rule's plan is executed independently so one rule's delay or
    failure never blocks another.
    """
    if maintenance_mode:
        logger.debug(
            "alert_eval_suppressed_maintenance",
            extra={"device_id": event.device_id},
        )
        return 0

    dispatched = 0
    for rule_id, nodes, edges in rules:
        plan = evaluate(nodes, edges, event.data, maintenance_mode=False)
        if not plan.steps:
            continue
        rule_event = TelemetryEvent(
            org_id=event.org_id,
            device_id=event.device_id,
            data=event.data,
            rule_id=rule_id,
        )
        dispatched += await execute_plan(plan, rule_event, sink, sleep_fn=sleep_fn)
    return dispatched


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
# A telemetry source yields TelemetryEvents until the worker stops.
TelemetrySource = Callable[[], "Awaitable[Optional[TelemetryEvent]]"]


async def run(
    telemetry_source: TelemetrySource,
    load_rules: RuleLoader,
    is_maintenance: MaintenanceCheck,
    sink: ActionSink,
    stop_event: Optional[asyncio.Event] = None,
    *,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Consume telemetry and evaluate rules until ``stop_event`` is set.

    Each loop pulls one :class:`TelemetryEvent` from ``telemetry_source``, skips
    devices in Maintenance_Mode (Req 5.7), loads the org's enabled rules, and
    runs each matching chain's actions through ``sink``. A failure handling one
    event is logged and the loop continues so a single bad sample never stops
    the worker. Each event is dispatched to its own task so a rule's delay does
    not stall ingestion of subsequent telemetry.
    """
    stop_event = stop_event or asyncio.Event()
    pending: set[asyncio.Task[Any]] = set()

    while not stop_event.is_set():
        event = await telemetry_source()
        if event is None:
            continue

        async def _handle(ev: TelemetryEvent) -> None:
            try:
                if await is_maintenance(ev.device_id):
                    logger.debug(
                        "alert_eval_suppressed_maintenance",
                        extra={"device_id": ev.device_id},
                    )
                    return
                rules = await load_rules(ev.org_id)
                await evaluate_event(
                    ev, rules, maintenance_mode=False, sink=sink, sleep_fn=sleep_fn
                )
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception(
                    "alert_event_failed",
                    extra={"org_id": ev.org_id, "device_id": ev.device_id},
                )

        task = asyncio.ensure_future(_handle(event))
        pending.add(task)
        task.add_done_callback(pending.discard)

    # Drain in-flight evaluations (including pending delays) before exiting.
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def main() -> None:  # pragma: no cover - process entry point wires live infra
    """Process entry point (``python -m app.workers.alert_checker``).

    Wires a Redis pub/sub telemetry source, DB-backed rule/device loaders, and a
    :class:`RedisActionSink`, then runs the evaluation loop with graceful
    shutdown - mirroring the other workers' ``main`` structure.
    """
    configure_logging()
    logger.info("alert_checker_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        from app.core.redis_client import get_redis

        redis = get_redis()
        if redis is None:
            raise RuntimeError("Redis client unavailable; cannot run Alert_Checker")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass

        # Subscribe to the cross-device telemetry pub/sub fan-out the
        # Batch_Writer publishes (Req 6.3); each message becomes a TelemetryEvent.
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"{rk.NAMESPACE}{rk.SEP}telemetry{rk.SEP}*")

        async def _source() -> Optional[TelemetryEvent]:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if not message:
                return None
            try:
                payload = json.loads(message["data"])
            except (ValueError, TypeError, KeyError):
                return None
            device_id = payload.get("device_id")
            if not device_id:
                return None
            return TelemetryEvent(
                org_id=str(payload.get("org_id", "")),
                device_id=str(device_id),
                data=payload.get("data") or {},
            )

        sink = RedisActionSink(redis)
        await run(_source, _load_rules, _device_in_maintenance, sink, stop_event=stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("alert_checker_stopped")


async def _load_rules(  # pragma: no cover - exercised against a live DB
    org_id: str,
) -> Sequence[tuple[str, Sequence[Any], Sequence[Any]]]:
    """Load an org's enabled rules with their node/edge graphs."""
    import uuid

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.rule import Rule, RuleEdge, RuleNode

    org_uuid = uuid.UUID(str(org_id))
    out: list[tuple[str, Sequence[Any], Sequence[Any]]] = []
    async with async_session_factory() as session:
        rules = (
            await session.execute(
                select(Rule).where(Rule.org_id == org_uuid, Rule.enabled.is_(True))
            )
        ).scalars().all()
        for rule in rules:
            nodes = (
                await session.execute(
                    select(RuleNode).where(RuleNode.rule_id == rule.id)
                )
            ).scalars().all()
            edges = (
                await session.execute(
                    select(RuleEdge).where(RuleEdge.rule_id == rule.id)
                )
            ).scalars().all()
            out.append((str(rule.id), list(nodes), list(edges)))
    return out


async def _device_in_maintenance(device_id: str) -> bool:  # pragma: no cover - live DB
    """Return whether a device is currently in Maintenance_Mode (Req 5.7)."""
    import uuid

    from app.db.session import async_session_factory
    from app.models.device import Device

    async with async_session_factory() as session:
        device = await session.get(Device, uuid.UUID(str(device_id)))
        return bool(device and device.maintenance_mode)


if __name__ == "__main__":
    main()
