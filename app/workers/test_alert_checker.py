"""Unit tests for the Alert_Checker worker (Task 10.3, Req 10.2, 10.3, 10.4, 5.7).

These exercise the pure planning core and the async executor with injected
fakes, so no live Redis, broker, or database is required:

- ``build_chain`` orders a rule_nodes/rule_edges graph from its trigger.
- ``plan_chain`` honours the trigger -> condition -> delay -> action flow.
- Maintenance_Mode suppresses evaluation entirely (Req 5.7).
- a false condition stops the chain before any following action runs.
- a delay defers everything after it (executor awaits the delay).
- ``RedisActionSink`` publishes command/notify/webhook side effects.
"""

from __future__ import annotations

import asyncio
import json

import fakeredis.aioredis
import pytest

from app.core import redis_keys as rk
from app.workers import alert_checker as ac


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------
def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "node_type": node_type, "config": config or {}}


def _edge(from_id: str, to_id: str) -> dict:
    return {"from": from_id, "to": to_id}


# ---------------------------------------------------------------------------
# build_chain
# ---------------------------------------------------------------------------
def test_build_chain_orders_from_trigger():
    nodes = [
        _node("a", "action", {"action": "notify"}),
        _node("t", "trigger", {"key": "temp", "op": "gt", "value": 30}),
        _node("c", "condition", {"key": "temp", "op": "lt", "value": 100}),
    ]
    edges = [_edge("t", "c"), _edge("c", "a")]

    chain = ac.build_chain(nodes, edges)

    assert [n.id for n in chain] == ["t", "c", "a"]
    assert [n.node_type for n in chain] == [
        ac.NodeType.TRIGGER,
        ac.NodeType.CONDITION,
        ac.NodeType.ACTION,
    ]


def test_build_chain_without_trigger_is_empty():
    nodes = [_node("c", "condition", {"key": "temp"})]
    assert ac.build_chain(nodes, []) == []


def test_build_chain_breaks_cycles():
    nodes = [_node("t", "trigger", {}), _node("a", "action", {"action": "notify"})]
    edges = [_edge("t", "a"), _edge("a", "t")]  # cycle back to trigger

    chain = ac.build_chain(nodes, edges)

    assert [n.id for n in chain] == ["t", "a"]


# ---------------------------------------------------------------------------
# plan_chain: maintenance mode (Req 5.7)
# ---------------------------------------------------------------------------
def test_maintenance_mode_suppresses_evaluation():
    chain = ac.build_chain(
        [_node("t", "trigger", {}), _node("a", "action", {"action": "notify"})],
        [_edge("t", "a")],
    )

    plan = ac.plan_chain(chain, {"temp": 50}, maintenance_mode=True)

    assert plan.suppressed is True
    assert plan.steps == ()
    assert plan.actions == []


# ---------------------------------------------------------------------------
# plan_chain: trigger + condition gating (Req 10.2)
# ---------------------------------------------------------------------------
def test_trigger_must_match_for_action():
    chain = ac.build_chain(
        [
            _node("t", "trigger", {"key": "temp", "op": "gt", "value": 30}),
            _node("a", "action", {"action": "notify"}),
        ],
        [_edge("t", "a")],
    )

    fired = ac.plan_chain(chain, {"temp": 40}, maintenance_mode=False)
    not_fired = ac.plan_chain(chain, {"temp": 10}, maintenance_mode=False)

    assert [n.id for n in fired.actions] == ["a"]
    assert not_fired.actions == []
    assert not_fired.suppressed is False


def test_false_condition_stops_chain_before_action():
    chain = ac.build_chain(
        [
            _node("t", "trigger", {"key": "temp", "op": "gt", "value": 30}),
            _node("c", "condition", {"key": "hum", "op": "lt", "value": 50}),
            _node("a", "action", {"action": "notify"}),
        ],
        [_edge("t", "c"), _edge("c", "a")],
    )

    blocked = ac.plan_chain(chain, {"temp": 40, "hum": 80}, maintenance_mode=False)
    passed = ac.plan_chain(chain, {"temp": 40, "hum": 20}, maintenance_mode=False)

    assert blocked.actions == []
    assert [n.id for n in passed.actions] == ["a"]


# ---------------------------------------------------------------------------
# plan_chain: delay (Req 10.3)
# ---------------------------------------------------------------------------
def test_delay_node_emits_delay_step_before_action():
    chain = ac.build_chain(
        [
            _node("t", "trigger", {}),
            _node("d", "delay", {"seconds": 5}),
            _node("a", "action", {"action": "command", "type": "off"}),
        ],
        [_edge("t", "d"), _edge("d", "a")],
    )

    plan = ac.plan_chain(chain, {"temp": 1}, maintenance_mode=False)

    assert isinstance(plan.steps[0], ac.DelayStep)
    assert plan.steps[0].seconds == 5
    assert isinstance(plan.steps[1], ac.ActionStep)
    assert plan.total_delay == 5


def test_delay_supports_milliseconds():
    chain = ac.build_chain(
        [_node("t", "trigger", {}), _node("d", "delay", {"ms": 2500})],
        [_edge("t", "d")],
    )
    plan = ac.plan_chain(chain, {}, maintenance_mode=False)
    assert plan.total_delay == 2.5


# ---------------------------------------------------------------------------
# execute_plan: delays are awaited before following actions (Req 10.3)
# ---------------------------------------------------------------------------
def test_execute_plan_awaits_delay_before_action():
    chain = ac.build_chain(
        [
            _node("t", "trigger", {}),
            _node("d", "delay", {"seconds": 3}),
            _node("a", "action", {"action": "notify"}),
        ],
        [_edge("t", "d"), _edge("d", "a")],
    )
    plan = ac.plan_chain(chain, {}, maintenance_mode=False)

    slept: list[float] = []
    dispatched: list[ac.Action] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def sink(action, event):
        # Action runs only after the delay was awaited.
        assert slept == [3]
        dispatched.append(action)

    event = ac.TelemetryEvent(org_id="o", device_id="d", data={}, rule_id="r")
    count = asyncio.run(ac.execute_plan(plan, event, sink, sleep_fn=fake_sleep))

    assert slept == [3]
    assert count == 1
    assert dispatched[0].kind is ac.ActionKind.NOTIFY


# ---------------------------------------------------------------------------
# RedisActionSink side effects
# ---------------------------------------------------------------------------
def test_redis_sink_publishes_notify_alert():
    async def run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(rk.device_channel("dev-1"))

        sink = ac.RedisActionSink(redis)
        action = ac.Action(ac.ActionKind.NOTIFY, {"message": "too hot"})
        event = ac.TelemetryEvent(org_id="o", device_id="dev-1", data={}, rule_id="rule-1")
        await sink(action, event)

        # Read past the subscribe confirmation to the published message.
        msg = None
        for _ in range(5):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if msg:
                break
        assert msg is not None
        body = json.loads(msg["data"])
        assert body["type"] == "alert"
        assert body["rule_id"] == "rule-1"
        assert body["message"] == "too hot"

    asyncio.run(run())


def test_redis_sink_publishes_command_via_publisher():
    async def run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        published: list[tuple[str, str]] = []

        async def publisher(topic, payload):
            published.append((topic, payload))

        sink = ac.RedisActionSink(redis, publisher=publisher)
        action = ac.Action(ac.ActionKind.COMMAND, {"action": "command", "type": "off"})
        event = ac.TelemetryEvent(org_id="org-1", device_id="dev-1", data={}, rule_id="r")
        await sink(action, event)

        assert len(published) == 1
        topic, payload = published[0]
        assert "org-1" in topic and "dev-1" in topic and topic.endswith("command")
        assert json.loads(payload)["type"] == "off"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# evaluate_event: maintenance suppresses, multiple rules independent
# ---------------------------------------------------------------------------
def test_evaluate_event_suppressed_in_maintenance():
    async def run():
        calls: list[ac.Action] = []

        async def sink(action, event):
            calls.append(action)

        nodes = [_node("t", "trigger", {}), _node("a", "action", {"action": "notify"})]
        edges = [_edge("t", "a")]
        event = ac.TelemetryEvent(org_id="o", device_id="d", data={"temp": 99})

        dispatched = await ac.evaluate_event(
            event, [("rule-1", nodes, edges)], maintenance_mode=True, sink=sink
        )
        assert dispatched == 0
        assert calls == []

    asyncio.run(run())


def test_evaluate_event_runs_matching_rules():
    async def run():
        calls: list[str] = []

        async def sink(action, event):
            calls.append(event.rule_id)

        nodes = [
            _node("t", "trigger", {"key": "temp", "op": "gt", "value": 30}),
            _node("a", "action", {"action": "notify"}),
        ]
        edges = [_edge("t", "a")]
        event = ac.TelemetryEvent(org_id="o", device_id="d", data={"temp": 40})

        async def nosleep(_):
            return None

        dispatched = await ac.evaluate_event(
            event,
            [("rule-1", nodes, edges), ("rule-2", nodes, edges)],
            maintenance_mode=False,
            sink=sink,
            sleep_fn=nosleep,
        )
        assert dispatched == 2
        assert set(calls) == {"rule-1", "rule-2"}

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Predicate edge cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "config,data,expected",
    [
        ({"key": "t", "op": "gt", "value": 5}, {"t": 6}, True),
        ({"key": "t", "op": "gt", "value": 5}, {"t": 5}, False),
        ({"key": "t", "op": "gte", "value": 5}, {"t": 5}, True),
        ({"key": "t", "op": "lt", "value": 5}, {"t": 4}, True),
        ({"key": "t", "op": "eq", "value": 5}, {"t": 5}, True),
        ({"key": "t"}, {"t": 5}, True),
        ({"key": "missing", "op": "gt", "value": 5}, {"t": 5}, False),
        ({}, {"t": 5}, True),
        ({"key": "t", "op": "bogus", "value": 5}, {"t": 5}, False),
    ],
)
def test_evaluate_predicate(config, data, expected):
    assert ac.evaluate_predicate(config, data) is expected


def test_evaluate_predicate_reads_data_envelope():
    assert ac.evaluate_predicate({"key": "t", "op": "gt", "value": 1}, {"data": {"t": 5}}) is True
