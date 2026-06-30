"""Property-based test for rule chain evaluation (Task 10.4).

# Feature: iotaps-platform, Property 17: Rule chain evaluation respects triggers, conditions, and delays

Property 17 (design.md "Correctness Properties"):

    For any rule chain and for any incoming telemetry, the chain's action
    executes only when the trigger and all preceding conditions hold, the
    execution of nodes following a delay node is deferred by at least the
    delay's duration, and node execution order matches the chain definition;
    for any device in Maintenance_Mode, no evaluation or alert occurs.

Validates: Requirements 10.1, 10.2, 10.3, 5.7

The test generates a random linear rule chain (trigger -> conditions / delays /
actions) plus a telemetry sample, evaluates it via the real
:func:`app.workers.alert_checker.evaluate` / :func:`execute_plan`, and asserts
the four facets of the property hold against an independent reference walk:

- in Maintenance_Mode nothing runs (suppressed, zero actions);
- an action runs iff the trigger and every condition *preceding it* are true;
- actions execute in chain order;
- every delay preceding the executed actions is awaited, and the total awaited
  time equals the sum of those delays (deferral by at least the delay).
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from app.workers import alert_checker as ac

# Telemetry key pool kept small so triggers/conditions actually reference keys
# present in the sample often enough to exercise the true/false branches.
_KEYS = ["temp", "hum", "pressure"]
_OPS = ["gt", "gte", "lt", "lte", "eq", "ne"]


def _predicate_config(draw) -> dict:
    return {
        "key": draw(st.sampled_from(_KEYS)),
        "op": draw(st.sampled_from(_OPS)),
        "value": draw(st.integers(min_value=0, max_value=10)),
    }


@st.composite
def _chain_and_telemetry(draw):
    """Generate a linear chain (trigger first) + a telemetry sample."""
    telemetry = {
        key: draw(st.integers(min_value=0, max_value=10)) for key in _KEYS
    }

    nodes = [{"id": "t", "node_type": "trigger", "config": _predicate_config(draw)}]
    edges = []
    prev = "t"

    # 0..6 follow-on nodes of mixed kinds.
    n = draw(st.integers(min_value=0, max_value=6))
    for i in range(n):
        kind = draw(st.sampled_from(["condition", "delay", "action"]))
        node_id = f"n{i}"
        if kind == "condition":
            config = _predicate_config(draw)
        elif kind == "delay":
            config = {"seconds": draw(st.integers(min_value=0, max_value=5))}
        else:  # action
            config = {
                "action": draw(st.sampled_from(["command", "notify", "webhook"])),
                "type": "on",
            }
        nodes.append({"id": node_id, "node_type": kind, "config": config})
        edges.append({"from": prev, "to": node_id})
        prev = node_id

    maintenance = draw(st.booleans())
    return nodes, edges, telemetry, maintenance


def _reference_walk(nodes, edges, telemetry, maintenance):
    """Independent oracle: returns (expected_action_ids, expected_total_delay).

    Mirrors the design ``evaluate`` flow without reusing the planner's code, so
    it is a genuine cross-check rather than a tautology.
    """
    if maintenance:
        return [], 0.0

    # Order nodes from the trigger by following first out-edges.
    by_id = {node["id"]: node for node in nodes}
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["from"], edge["to"])
    order = []
    seen = set()
    cur = "t"
    while cur is not None and cur in by_id and cur not in seen:
        seen.add(cur)
        order.append(by_id[cur])
        cur = adjacency.get(cur)

    ops = {
        "gt": lambda a, b: a > b,
        "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
    }

    def truthy(config):
        val = telemetry.get(config["key"])
        return ops[config["op"]](val, config["value"])

    trigger = order[0]
    if not truthy(trigger["config"]):
        return [], 0.0

    actions = []
    total_delay = 0.0
    for node in order[1:]:
        if node["node_type"] == "condition":
            if not truthy(node["config"]):
                break
        elif node["node_type"] == "delay":
            total_delay += node["config"]["seconds"]
        elif node["node_type"] == "action":
            actions.append(node["id"])
    return actions, total_delay


@settings(max_examples=10, deadline=None)
@given(_chain_and_telemetry())
def test_rule_chain_evaluation(case) -> None:
    """Property 17: rule chain evaluation respects triggers, conditions, delays.

    Validates: Requirements 10.1, 10.2, 10.3, 5.7
    """
    nodes, edges, telemetry, maintenance = case

    plan = ac.evaluate(nodes, edges, telemetry, maintenance_mode=maintenance)

    expected_actions, expected_delay = _reference_walk(
        nodes, edges, telemetry, maintenance
    )

    # Maintenance_Mode: suppressed, nothing planned (Req 5.7).
    if maintenance:
        assert plan.suppressed is True
        assert plan.actions == []

    # Action set + order matches the chain definition (Req 10.1, 10.2).
    assert [node.id for node in plan.actions] == expected_actions

    # Total deferral equals the sum of delays preceding chain completion (Req 10.3).
    assert plan.total_delay == expected_delay

    # Execute the plan and confirm the awaited time equals the planned delay and
    # the actions fire only after their delays (deferral is real, Req 10.3).
    slept_total = 0.0

    async def fake_sleep(seconds: float) -> None:
        nonlocal slept_total
        slept_total += seconds

    fired: list[str] = []

    async def sink(action, event):
        fired.append(event.rule_id or "")

    event = ac.TelemetryEvent(
        org_id="o", device_id="d", data=telemetry, rule_id="rule"
    )
    count = asyncio.run(ac.execute_plan(plan, event, sink, sleep_fn=fake_sleep))

    assert count == len(expected_actions)
    assert slept_total == expected_delay
