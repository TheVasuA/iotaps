"""Property-based test for plan-dependent telemetry retention (Task 6.4).

# Feature: iotaps-platform, Property 7: Retention deletes only expired telemetry

Property 7 (design.md "Correctness Properties"):

    For any set of telemetry rows with various timestamps and any plan, after the
    Data_Retention worker runs, exactly the rows strictly older than the plan's
    cutoff are deleted and all rows at or after the cutoff are retained.

Validates: Requirements 6.7, 6.8, 15.1

The test drives the real :func:`app.workers.data_retention.purge_expired_telemetry`
core with an injected in-memory store that implements the ``execute_fn`` /
:class:`~app.workers.data_retention.PurgeOp` contract, so no live TimescaleDB is
required. The store holds raw (``telemetry``/``ts``) rows for several orgs on
mixed plans; each generated row carries an absolute timestamp.

The Data_Retention worker only purges the raw ``telemetry`` hypertable: the
downsampled tiers (``telemetry_5m``/``1h``/``1d``) are TimescaleDB continuous
aggregates that cannot be ``DELETE``d from directly, so their retention is
managed by TimescaleDB's own aggregate retention policy rather than this worker
(see ``data_retention.plan_purge_ops``). After the sweep we assert, per org,
that the surviving raw rows are exactly those at or after that plan's raw cutoff
(``now - raw_max_age``) and every deleted row was strictly older than it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.workers import data_retention as dr

# Fixed reference instant the sweep runs at; generated timestamps are offsets
# (in hours) around it so rows fall on both sides of every plan cutoff.
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# A small org pool so generated rows share orgs and plans collide/repeat.
_ORG_IDS = [f"org-{i}" for i in range(3)]

# Plans include recognised plans plus unknown/ambiguous values that must fall
# back to the Free policy (Req 15.7) so the cutoff is still well defined.
_PLANS = ["free", "pro", "FREE", " Pro ", None, "", "enterprise", "bogus"]

# Hours offset from _NOW. The 500-day span (in hours) straddles the longest raw
# retention window (Pro raw = 90 days), so rows land older and newer than every
# cutoff, and the ``0`` boundary case (exactly at a cutoff) is reachable.
_MIN_OFFSET_H = -500 * 24
_MAX_OFFSET_H = 24


class InMemoryStore:
    """In-memory telemetry store honouring the execute_fn / PurgeOp contract.

    Rows are ``(org_id, table, time_column, timestamp)`` tuples. Calling the
    store with a :class:`~app.workers.data_retention.PurgeOp` deletes the rows
    for that org/table whose timestamp is strictly older than ``op.cutoff`` and
    returns the number removed, exactly like the real asyncpg-backed
    ``delete_expired`` (``WHERE org_id = :org_id AND <col> < :cutoff``).
    """

    def __init__(self, rows: list[tuple[str, str, str, datetime]]) -> None:
        # Keep a list of live rows; preserve insertion so survivors stay stable.
        self.rows = list(rows)

    async def __call__(self, op: dr.PurgeOp) -> int:
        survivors: list[tuple[str, str, str, datetime]] = []
        deleted = 0
        for row in self.rows:
            org_id, table, time_column, ts = row
            matches = (
                org_id == op.org_id
                and table == op.table
                and time_column == op.time_column
            )
            if matches and ts < op.cutoff:
                deleted += 1
            else:
                survivors.append(row)
        self.rows = survivors
        return deleted


# One generated telemetry row: an org, the raw telemetry tier and an offset.
# The worker only purges the raw hypertable (the downsampled continuous
# aggregates cannot be DELETEd from), so every generated row targets the raw
# tier.
_row = st.fixed_dictionaries(
    {
        "org": st.sampled_from(_ORG_IDS),
        "tier": st.just((dr.RAW_TABLE, dr.RAW_TIME_COLUMN)),
        "offset_h": st.integers(min_value=_MIN_OFFSET_H, max_value=_MAX_OFFSET_H),
    }
)


async def _run(rows_spec: list[dict], plan_assignment: list[int]) -> None:
    # Assign each org a plan from the generated indices (wrap if shorter).
    org_plan: dict[str, str | None] = {}
    for i, org in enumerate(_ORG_IDS):
        idx = plan_assignment[i % len(plan_assignment)] if plan_assignment else 0
        org_plan[org] = _PLANS[idx % len(_PLANS)]

    # Materialise the generated rows into the store.
    rows: list[tuple[str, str, str, datetime]] = []
    for spec in rows_spec:
        table, time_column = spec["tier"]
        ts = _NOW + timedelta(hours=spec["offset_h"])
        rows.append((spec["org"], table, time_column, ts))

    store = InMemoryStore(rows)
    original = list(rows)

    orgs = [(org, plan) for org, plan in org_plan.items()]
    await dr.purge_expired_telemetry(store, orgs, _NOW)

    # Compute the expected cutoff for every (org, table) pair.
    def cutoff_for(org: str, table: str) -> datetime:
        policy = dr.policy_for_plan(org_plan[org])
        max_age = policy.raw_max_age if table == dr.RAW_TABLE else policy.hourly_max_age
        return _NOW - max_age

    expected_survivors = [
        row for row in original if row[3] >= cutoff_for(row[0], row[1])
    ]

    # Survivors are exactly the rows at or after their tier's cutoff (counting
    # duplicates): nothing expired was kept, nothing live was dropped, and every
    # deleted row was strictly older than its cutoff (Property 7 / Req 6.7, 6.8).
    assert sorted(store.rows) == sorted(expected_survivors)

    # Defensive cross-check: no surviving row is older than its tier's cutoff.
    for org_id, table, _col, ts in store.rows:
        assert ts >= cutoff_for(org_id, table)


@settings(max_examples=10, deadline=None)
@given(
    rows_spec=st.lists(_row, min_size=0, max_size=60),
    plan_assignment=st.lists(
        st.integers(min_value=0, max_value=len(_PLANS) - 1),
        min_size=1,
        max_size=len(_ORG_IDS),
    ),
)
def test_retention_deletes_only_expired_telemetry(
    rows_spec: list[dict], plan_assignment: list[int]
) -> None:
    """Property 7: retention deletes only expired telemetry.

    Validates: Requirements 6.7, 6.8, 15.1
    """
    asyncio.run(_run(rows_spec, plan_assignment))
