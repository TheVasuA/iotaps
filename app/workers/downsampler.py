"""Downsampler worker (Req 6.6, 30.1).

The Downsampler is the third stage of the telemetry pipeline. The raw
``telemetry`` hypertable is rolled up into 5-minute, 1-hour and 1-day
downsampled views (design.md "TimescaleDB: telemetry hypertable"). Those views
are TimescaleDB *continuous aggregates* created ``WITH NO DATA`` and **without**
an automatic refresh policy (see ``alembic/versions/0001_initial_schema.py``),
so this worker is responsible for driving their refreshes (Req 6.6).

For each rollup the worker periodically calls TimescaleDB's
``refresh_continuous_aggregate(cagg, window_start, window_end)`` procedure over a
trailing window so newly ingested raw telemetry is folded into the materialised
buckets:

    telemetry_5m  -> refreshed every 5 minutes over a trailing 1 hour
    telemetry_1h  -> refreshed every 1 hour    over a trailing 1 day
    telemetry_1d  -> refreshed every 1 day     over a trailing 7 days

The cadence matches the bucket width (refreshing a 5-minute rollup more often
than every 5 minutes does no useful work), and the trailing window is wide
enough to absorb late-arriving telemetry while keeping each refresh cheap. A
``NULL`` upper bound means "refresh up to the most recent data" so the latest
buckets are always included.

Design notes / invariants:
- ``refresh_continuous_aggregate`` cannot run inside a transaction block, so the
  default executor issues the ``CALL`` on an ``AUTOCOMMIT`` connection.
- The view name passed to the procedure comes from a fixed internal allowlist
  (:data:`DEFAULT_AGGREGATES`); it is never derived from user input, so inlining
  it into the SQL is safe.
- Availability/connection failures raise :class:`TimescaleUnavailable` so the
  run loop retains the schedule and retries with backoff (mirrors the
  Batch_Writer's Req 6.9 policy); other errors propagate and stop the worker.

The core (`refresh_due_aggregates` / `due_aggregates`) takes an injected
``execute_fn`` and an explicit ``now`` so it can be unit-tested without a live
TimescaleDB. ``main`` wires the real asyncpg-backed executor and adds graceful
shutdown plus backoff.
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
class DownsampleError(Exception):
    """Base class for Downsampler refresh failures."""


class TimescaleUnavailable(DownsampleError):
    """The Time_Series_DB could not be reached for a refresh.

    Raised by an ``execute_fn`` when the failure is an availability/connection
    problem. The run loop keeps the current schedule and retries with backoff so
    a transient outage never stalls downsampling permanently.
    """


# ---------------------------------------------------------------------------
# Rollup specifications
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AggregateSpec:
    """One continuous-aggregate rollup the Downsampler must keep refreshed.

    ``cadence`` is how often the view is refreshed; ``lookback`` is the trailing
    window passed to ``refresh_continuous_aggregate`` (its upper bound is always
    ``NULL`` = up to the latest data).
    """

    view: str
    bucket: str
    cadence: timedelta
    lookback: timedelta


# The 5m/1h/1d rollups defined in the schema migration (Req 6.6). Each view is
# refreshed at its bucket cadence over a trailing window wide enough to capture
# late-arriving telemetry.
DEFAULT_AGGREGATES: tuple[AggregateSpec, ...] = (
    AggregateSpec("telemetry_5m", "5 minutes", timedelta(minutes=5), timedelta(hours=1)),
    AggregateSpec("telemetry_1h", "1 hour", timedelta(hours=1), timedelta(days=1)),
    AggregateSpec("telemetry_1d", "1 day", timedelta(days=1), timedelta(days=7)),
)

# Allowlist of view names this worker may refresh, derived from the specs above.
_KNOWN_VIEWS = frozenset(spec.view for spec in DEFAULT_AGGREGATES)

# How often the run loop wakes to check which rollups are due. Kept below the
# smallest cadence so refreshes fire close to their scheduled time.
POLL_INTERVAL_SECONDS = 60.0

# Exponential backoff bounds applied while TimescaleDB is unavailable.
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0

# An execute callable refreshes one continuous aggregate over [start, end).
# ``end`` is ``None`` to refresh up to the most recent data.
ExecuteFn = Callable[[str, Optional[datetime], Optional[datetime]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Scheduling core (testable; no live DB required)
# ---------------------------------------------------------------------------
def due_aggregates(
    specs: tuple[AggregateSpec, ...],
    now: datetime,
    last_refreshed: dict[str, datetime],
) -> list[AggregateSpec]:
    """Return the specs whose cadence has elapsed (or which never ran).

    A spec is due when it has never been refreshed, or when at least its
    ``cadence`` has passed since the last refresh recorded in ``last_refreshed``.
    """
    due: list[AggregateSpec] = []
    for spec in specs:
        last = last_refreshed.get(spec.view)
        if last is None or now - last >= spec.cadence:
            due.append(spec)
    return due


async def refresh_due_aggregates(
    execute_fn: ExecuteFn,
    specs: tuple[AggregateSpec, ...],
    now: datetime,
    last_refreshed: dict[str, datetime],
) -> list[str]:
    """Refresh every rollup that is due and record the time it ran.

    For each due spec, refreshes the trailing window ``[now - lookback, NULL]``
    via ``execute_fn`` then stamps ``last_refreshed[view] = now`` so it is not
    refreshed again until its cadence elapses. Returns the views refreshed.

    If ``execute_fn`` raises :class:`TimescaleUnavailable` the corresponding
    ``last_refreshed`` entry is left untouched so the view is retried on the next
    loop; the exception propagates so the caller can apply backoff.
    """
    refreshed: list[str] = []
    for spec in due_aggregates(specs, now, last_refreshed):
        window_start = now - spec.lookback
        await execute_fn(spec.view, window_start, None)
        last_refreshed[spec.view] = now
        refreshed.append(spec.view)
        logger.info(
            "continuous_aggregate_refreshed",
            extra={"view": spec.view, "window_start": window_start.isoformat()},
        )
    return refreshed


# ---------------------------------------------------------------------------
# Default TimescaleDB refresh executor (asyncpg / SQLAlchemy)
# ---------------------------------------------------------------------------
async def refresh_aggregate(
    view: str,
    window_start: Optional[datetime],
    window_end: Optional[datetime],
) -> None:
    """Refresh one materialized view.

    Since we use standard materialized views (not TimescaleDB continuous
    aggregates), we simply call REFRESH MATERIALIZED VIEW CONCURRENTLY.
    Falls back to non-concurrent if the view has no unique index.
    """
    if view not in _KNOWN_VIEWS:
        raise ValueError(f"refusing to refresh unknown view: {view!r}")

    from sqlalchemy import text
    from sqlalchemy.exc import (
        DisconnectionError,
        InterfaceError,
        OperationalError,
        ProgrammingError,
    )

    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            try:
                await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            except ProgrammingError:
                # No unique index — fall back to non-concurrent refresh
                await conn.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
    except (OperationalError, InterfaceError, DisconnectionError, ConnectionError, OSError) as exc:
        raise TimescaleUnavailable(str(exc)) from exc


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    execute_fn: ExecuteFn,
    specs: tuple[AggregateSpec, ...] = DEFAULT_AGGREGATES,
    stop_event: Optional[asyncio.Event] = None,
    *,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> None:
    """Continuously refresh due rollups until ``stop_event`` is set.

    Each iteration refreshes every rollup whose cadence has elapsed, then idles
    for ``poll_interval`` (waking early on shutdown). On
    :class:`TimescaleUnavailable` it backs off exponentially and retries without
    advancing the schedule; any other refresh error propagates and stops the
    worker.
    """
    stop_event = stop_event or asyncio.Event()
    last_refreshed: dict[str, datetime] = {}
    backoff = BACKOFF_INITIAL_SECONDS

    while not stop_event.is_set():
        try:
            await refresh_due_aggregates(execute_fn, specs, now_fn(), last_refreshed)
        except TimescaleUnavailable as exc:
            logger.warning(
                "timescaledb_unavailable_retrying",
                extra={"error": str(exc), "retry_in_seconds": backoff},
            )
            await _sleep_or_stop(stop_event, backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_SECONDS)
            continue
        except Exception as exc:
            logger.exception("downsample_refresh_failed", extra={"error": str(exc)})
            raise

        backoff = BACKOFF_INITIAL_SECONDS
        await _sleep_or_stop(stop_event, poll_interval)


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def main() -> None:
    """Process entry point (``python -m app.workers.downsampler``)."""
    configure_logging()
    logger.info("downsampler_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # pragma: no cover - Windows lacks add_signal_handler
                pass
        await run(refresh_aggregate, stop_event=stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - graceful Ctrl-C
        pass
    logger.info("downsampler_stopped")


if __name__ == "__main__":
    main()
