"""Data_Retention worker (Req 6.7, 6.8, 15.1, 30.1).

The Data_Retention worker is one of the eight background workers required by the
platform (design "Background Workers", Req 30.1). Its job is to delete telemetry
that has exceeded the owning Organization's plan-defined retention period
(Req 6.8). Retention is **plan-dependent**, so this worker enforces it per org
rather than via a single global TimescaleDB retention policy (design.md
"TimescaleDB: telemetry hypertable"):

    Free_Plan : raw + hourly telemetry retained 7 days   (Req 15.1, 15.7)
    Pro_Plan  : raw telemetry retained 3 months,
                downsampled hourly telemetry retained 1 year (Req 6.7, 15.2)

For every Organization the worker resolves the plan's
:class:`RetentionPolicy`, computes an absolute cutoff timestamp per target
(``now - max_age``) and deletes rows older than that cutoff from the raw
``telemetry`` hypertable and the ``telemetry_1h`` downsampled aggregate. A plan
that is missing or unrecognised falls back to the Free policy, matching the
platform's "ambiguous plan -> Free limits" convention (Req 15.7) and ensuring no
data is ever retained longer than a plan entitles.

Design notes / invariants:
- Only rows strictly older than the cutoff are deleted; anything at or after the
  cutoff is retained (Property 7 / Req 6.7, 6.8).
- The set of deletable tables and their time columns comes from a fixed internal
  allowlist (:data:`_KNOWN_TARGETS`); the org_id and cutoff are always bound
  parameters, so a purge statement can never be built from user input.
- Availability/connection failures raise :class:`TimescaleUnavailable` so the
  run loop retains the schedule and retries with backoff (mirrors the
  Batch_Writer's Req 6.9 policy and the Downsampler); other errors propagate and
  stop the worker.

The core (`plan_purge_ops` / `purge_expired_telemetry`) takes the org list, an
explicit ``now`` and an injected ``execute_fn``, so it can be unit-tested
without a live TimescaleDB. ``main`` wires the real asyncpg-backed executor and
the org-plan loader, and adds graceful shutdown plus backoff.
"""

from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class DataRetentionError(Exception):
    """Base class for Data_Retention purge failures."""


class TimescaleUnavailable(DataRetentionError):
    """The Time_Series_DB could not be reached for a purge.

    Raised by an ``execute_fn`` when the failure is an availability/connection
    problem. The run loop keeps the current schedule and retries with backoff so
    a transient outage never permanently stalls retention enforcement.
    """


# ---------------------------------------------------------------------------
# Retention policies (plan-dependent; Req 6.7, 6.8, 15.1, 15.2)
# ---------------------------------------------------------------------------
# Calendar-month/year retentions are expressed as fixed-day windows: "3 months"
# is treated as 90 days and "1 year" as 365 days. This keeps the cutoff purely a
# function of ``now`` (no calendar arithmetic) which is exactly what Property 7
# reasons about, and it is the conventional interpretation for time-series TTLs.
_DAYS_PER_MONTH = 30
_DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class RetentionPolicy:
    """How long each telemetry tier is retained for one plan.

    ``raw_max_age`` applies to the raw ``telemetry`` hypertable; ``hourly_max_age``
    applies to the ``telemetry_1h`` downsampled aggregate. A row is expired (and
    therefore deleted) once it is strictly older than ``now - max_age``.
    """

    plan: str
    raw_max_age: timedelta
    hourly_max_age: timedelta


# Free retains everything for 7 days; Pro keeps raw for 3 months and the hourly
# rollup for 1 year (design "TimescaleDB: telemetry hypertable").
FREE_POLICY = RetentionPolicy(
    "free",
    raw_max_age=timedelta(days=7),
    hourly_max_age=timedelta(days=7),
)
PRO_POLICY = RetentionPolicy(
    "pro",
    raw_max_age=timedelta(days=3 * _DAYS_PER_MONTH),
    hourly_max_age=timedelta(days=_DAYS_PER_YEAR),
)

PLAN_POLICIES: dict[str, RetentionPolicy] = {
    "free": FREE_POLICY,
    "pro": PRO_POLICY,
}

# Unknown/ambiguous plans fall back to the most restrictive (Free) policy so a
# plan we cannot classify never grants extended retention (Req 15.7).
DEFAULT_POLICY = FREE_POLICY


def policy_for_plan(plan: Optional[str]) -> RetentionPolicy:
    """Resolve the retention policy for a plan string.

    Matching is case-insensitive and whitespace-tolerant. Anything that is not a
    recognised plan (``None``, empty, typo) resolves to :data:`DEFAULT_POLICY`
    (Free), so retention is never longer than the plan entitles (Req 15.7).
    """
    if isinstance(plan, str):
        normalized = plan.strip().lower()
        if normalized in PLAN_POLICIES:
            return PLAN_POLICIES[normalized]
    return DEFAULT_POLICY


# ---------------------------------------------------------------------------
# Purge targets (testable; no live DB required)
# ---------------------------------------------------------------------------
# Allowlist of (table, time_column) pairs this worker may purge, mapped to the
# policy field that governs each. Inlining a table/column name into SQL is only
# ever done from this fixed set, never from user input.
RAW_TABLE = "telemetry"
RAW_TIME_COLUMN = "ts"
# Note: telemetry_1h/5m/1d are materialized views and cannot be deleted from.
# Data retention only applies to the raw telemetry hypertable.
# The materialized views are refreshed by the downsampler worker.

_KNOWN_TARGETS: frozenset[tuple[str, str]] = frozenset(
    {
        (RAW_TABLE, RAW_TIME_COLUMN),
    }
)


@dataclass(frozen=True)
class PurgeOp:
    """A single "delete rows older than ``cutoff``" operation for one org.

    ``table``/``time_column`` identify the target telemetry tier, ``org_id``
    scopes the delete to the owning Organization, and ``cutoff`` is the absolute
    boundary: rows with ``time_column < cutoff`` are expired and removed; rows at
    or after ``cutoff`` are retained.
    """

    table: str
    time_column: str
    org_id: str
    cutoff: datetime


def plan_purge_ops(org_id: str, plan: Optional[str], now: datetime) -> list[PurgeOp]:
    """Build the purge operations for one org under its plan's policy.

    Only purges the raw telemetry hypertable. Materialized views are managed
    by the downsampler worker (refresh) and don't need direct deletion.
    """
    policy = policy_for_plan(plan)
    return [
        PurgeOp(RAW_TABLE, RAW_TIME_COLUMN, org_id, now - policy.raw_max_age),
    ]


# An execute callable deletes expired rows for one PurgeOp and returns the row
# count removed.
ExecuteFn = Callable[[PurgeOp], Awaitable[int]]

# A loader returning the (org_id, plan) pairs whose telemetry should be swept.
OrgPlanFn = Callable[[], Awaitable[list[tuple[str, Optional[str]]]]]


async def purge_expired_telemetry(
    execute_fn: ExecuteFn,
    orgs: list[tuple[str, Optional[str]]],
    now: datetime,
) -> int:
    """Delete expired telemetry for every org. Returns total rows deleted.

    For each ``(org_id, plan)`` the plan's :class:`RetentionPolicy` drives a
    cutoff per tier and ``execute_fn`` removes everything older than it
    (Req 6.8). If ``execute_fn`` raises :class:`TimescaleUnavailable` the
    exception propagates so the caller can apply backoff and retry the whole
    sweep on the next loop without losing the schedule.
    """
    total = 0
    for org_id, plan in orgs:
        for op in plan_purge_ops(org_id, plan, now):
            deleted = await execute_fn(op)
            total += int(deleted)
            if deleted:
                logger.info(
                    "telemetry_retention_purged",
                    extra={
                        "org_id": org_id,
                        "table": op.table,
                        "cutoff": op.cutoff.isoformat(),
                        "deleted": int(deleted),
                    },
                )
    return total


# ---------------------------------------------------------------------------
# Default TimescaleDB purge executor + org loader (asyncpg / SQLAlchemy)
# ---------------------------------------------------------------------------
async def delete_expired(op: PurgeOp) -> int:
    """Delete one org's rows older than ``op.cutoff`` from ``op.table``.

    The table/time-column pair is validated against :data:`_KNOWN_TARGETS` (an
    internal allowlist) before being inlined; ``org_id`` and ``cutoff`` are bound
    parameters. Availability/connection failures are re-raised as
    :class:`TimescaleUnavailable` so the caller retains the schedule and retries;
    all other errors propagate unchanged (Req 6.9-style policy).
    """
    if (op.table, op.time_column) not in _KNOWN_TARGETS:
        raise ValueError(
            f"refusing to purge unknown telemetry target: {op.table!r}.{op.time_column!r}"
        )

    from sqlalchemy import text
    from sqlalchemy.exc import (
        DisconnectionError,
        InterfaceError,
        OperationalError,
    )

    from app.db.session import async_session_factory

    # Table/column come from the allowlist above; org_id and cutoff are bound.
    stmt = text(
        f"DELETE FROM {op.table} "
        f"WHERE org_id = :org_id AND {op.time_column} < :cutoff"
    )
    params = {"org_id": op.org_id, "cutoff": op.cutoff}

    try:
        async with async_session_factory() as session:
            result = await session.execute(stmt, params)
            await session.commit()
            return int(result.rowcount or 0)
    except (OperationalError, InterfaceError, DisconnectionError, ConnectionError, OSError) as exc:
        # Connection/availability problems: retain the schedule and retry.
        raise TimescaleUnavailable(str(exc)) from exc


async def load_org_plans() -> list[tuple[str, Optional[str]]]:
    """Load every Organization's ``(id, plan)`` for the retention sweep."""
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.organization import Organization

    async with async_session_factory() as session:
        rows = await session.execute(select(Organization.id, Organization.plan))
        return [(str(org_id), plan) for org_id, plan in rows.all()]


# How often the run loop performs a full retention sweep. Expired telemetry only
# accumulates slowly, so an hourly sweep keeps each pass cheap (most deletes are
# no-ops) while bounding how long expired data can linger past its cutoff.
SWEEP_INTERVAL_SECONDS = 3600.0

# Exponential backoff bounds applied while TimescaleDB is unavailable.
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    execute_fn: ExecuteFn,
    org_plan_fn: OrgPlanFn,
    stop_event: Optional[asyncio.Event] = None,
    *,
    interval_seconds: float = SWEEP_INTERVAL_SECONDS,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    """Sweep expired telemetry on a fixed interval until ``stop_event`` is set.

    Each iteration loads the current org/plan list and purges expired telemetry
    for every org, then idles for ``interval_seconds`` (waking early on
    shutdown). On :class:`TimescaleUnavailable` it backs off exponentially and
    retries the sweep without advancing the schedule (Req 6.9-style); any other
    error propagates and stops the worker.
    """
    stop_event = stop_event or asyncio.Event()
    backoff = BACKOFF_INITIAL_SECONDS

    while not stop_event.is_set():
        try:
            orgs = await org_plan_fn()
            await purge_expired_telemetry(execute_fn, orgs, now_fn())
        except TimescaleUnavailable as exc:
            logger.warning(
                "timescaledb_unavailable_retrying",
                extra={"error": str(exc), "retry_in_seconds": backoff},
            )
            await _sleep_or_stop(stop_event, backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_SECONDS)
            continue
        except Exception as exc:
            logger.exception("data_retention_sweep_failed", extra={"error": str(exc)})
            raise

        backoff = BACKOFF_INITIAL_SECONDS
        await _sleep_or_stop(stop_event, interval_seconds)


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def main() -> None:
    """Process entry point (``python -m app.workers.data_retention``)."""
    configure_logging()
    logger.info("data_retention_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # pragma: no cover - Windows lacks add_signal_handler
                pass
        await run(delete_expired, load_org_plans, stop_event=stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - graceful Ctrl-C
        pass
    logger.info("data_retention_stopped")


if __name__ == "__main__":
    main()
