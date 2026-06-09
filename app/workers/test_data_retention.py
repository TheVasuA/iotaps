"""Unit tests for the Data_Retention worker (Task 6.3, Req 6.7, 6.8, 15.1).

These cover the plan-dependent retention contract with an injected fake executor
and an explicit ``now``, so no live TimescaleDB is required:

- Free retains 7 days; Pro retains raw 3 months / hourly 1 year (Req 6.7, 15.1, 15.2)
- unknown/ambiguous plans fall back to the Free policy (Req 15.7)
- the cutoff is ``now - max_age`` per tier and only older rows are purged
- TimescaleUnavailable propagates so the run loop can back off and retry
- the default executor refuses unknown purge targets
- the run loop stops promptly on shutdown
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.workers import data_retention as dr


def _now() -> datetime:
    return datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FakeExecutor:
    """Records PurgeOp calls and returns a fixed deleted-row count."""

    def __init__(self, deleted: int = 0) -> None:
        self.ops: list[dr.PurgeOp] = []
        self._deleted = deleted

    async def __call__(self, op: dr.PurgeOp) -> int:
        self.ops.append(op)
        return self._deleted


# ---------------------------------------------------------------------------
# Plan -> policy resolution (Req 6.7, 15.1, 15.2, 15.7)
# ---------------------------------------------------------------------------
def test_free_policy_retains_seven_days():
    policy = dr.policy_for_plan("free")
    assert policy.raw_max_age == timedelta(days=7)
    assert policy.hourly_max_age == timedelta(days=7)


def test_pro_policy_retains_raw_three_months_hourly_one_year():
    policy = dr.policy_for_plan("pro")
    assert policy.raw_max_age == timedelta(days=90)
    assert policy.hourly_max_age == timedelta(days=365)


@pytest.mark.parametrize("plan", [None, "", "  ", "enterprise", "FREEMIUM", "unknown"])
def test_unknown_plan_falls_back_to_free(plan):
    assert dr.policy_for_plan(plan) is dr.FREE_POLICY


@pytest.mark.parametrize("plan,expected", [("FREE", "free"), (" Pro ", "pro"), ("pRo", "pro")])
def test_plan_matching_is_case_and_whitespace_insensitive(plan, expected):
    assert dr.policy_for_plan(plan) is dr.PLAN_POLICIES[expected]


# ---------------------------------------------------------------------------
# Cutoff computation (now - max_age per tier)
# ---------------------------------------------------------------------------
def test_plan_purge_ops_cutoffs_for_free():
    now = _now()
    ops = dr.plan_purge_ops("org-1", "free", now)
    by_table = {op.table: op for op in ops}

    assert by_table[dr.RAW_TABLE].cutoff == now - timedelta(days=7)
    assert by_table[dr.RAW_TABLE].time_column == dr.RAW_TIME_COLUMN
    assert by_table[dr.HOURLY_VIEW].cutoff == now - timedelta(days=7)
    assert by_table[dr.HOURLY_VIEW].time_column == dr.HOURLY_TIME_COLUMN
    assert all(op.org_id == "org-1" for op in ops)


def test_plan_purge_ops_cutoffs_for_pro():
    now = _now()
    ops = dr.plan_purge_ops("org-2", "pro", now)
    by_table = {op.table: op for op in ops}

    assert by_table[dr.RAW_TABLE].cutoff == now - timedelta(days=90)
    assert by_table[dr.HOURLY_VIEW].cutoff == now - timedelta(days=365)


# ---------------------------------------------------------------------------
# Sweep across orgs
# ---------------------------------------------------------------------------
async def test_purge_runs_both_tiers_per_org():
    execute = FakeExecutor(deleted=3)
    now = _now()
    orgs = [("org-a", "free"), ("org-b", "pro")]

    total = await dr.purge_expired_telemetry(execute, orgs, now)

    # 2 orgs x 2 tiers x 3 rows each.
    assert total == 12
    assert len(execute.ops) == 4
    tables = {(op.org_id, op.table) for op in execute.ops}
    assert tables == {
        ("org-a", dr.RAW_TABLE),
        ("org-a", dr.HOURLY_VIEW),
        ("org-b", dr.RAW_TABLE),
        ("org-b", dr.HOURLY_VIEW),
    }


async def test_purge_empty_org_list_deletes_nothing():
    execute = FakeExecutor(deleted=5)
    total = await dr.purge_expired_telemetry(execute, [], _now())
    assert total == 0
    assert execute.ops == []


# ---------------------------------------------------------------------------
# Availability failures propagate (retried by the run loop)
# ---------------------------------------------------------------------------
async def test_unavailable_executor_propagates():
    async def failing(op):
        raise dr.TimescaleUnavailable("connection refused")

    with pytest.raises(dr.TimescaleUnavailable):
        await dr.purge_expired_telemetry(failing, [("org-a", "free")], _now())


# ---------------------------------------------------------------------------
# Default executor guards against unknown targets
# ---------------------------------------------------------------------------
async def test_delete_expired_rejects_unknown_target():
    op = dr.PurgeOp("telemetry; DROP TABLE telemetry", "ts", "org-a", _now())
    with pytest.raises(ValueError):
        await dr.delete_expired(op)


# ---------------------------------------------------------------------------
# Run loop stops promptly on shutdown
# ---------------------------------------------------------------------------
async def test_run_stops_when_event_set():
    execute = FakeExecutor()

    async def orgs():
        return [("org-a", "free")]

    stop = asyncio.Event()
    stop.set()  # already requested -> loop exits without purging

    await dr.run(execute, orgs, stop_event=stop, interval_seconds=0.01)

    assert execute.ops == []


async def test_run_performs_one_sweep_then_stops():
    execute = FakeExecutor(deleted=1)
    calls = {"n": 0}

    async def orgs():
        return [("org-a", "pro")]

    stop = asyncio.Event()

    # now_fn fires the stop event after the first sweep so the loop exits.
    def now_fn():
        calls["n"] += 1
        stop.set()
        return _now()

    await dr.run(execute, orgs, stop_event=stop, interval_seconds=0.01, now_fn=now_fn)

    # One sweep over one org -> both tiers purged once.
    assert len(execute.ops) == 2
