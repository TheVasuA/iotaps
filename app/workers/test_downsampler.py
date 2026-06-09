"""Unit tests for the Downsampler worker (Task 6.1, Req 6.6, 30.1).

These cover the scheduling/refresh contract with an injected fake executor and
an explicit ``now``, so no live TimescaleDB is required:

- the 5m/1h/1d rollups are all defined and refreshed (Req 6.6)
- a rollup is due on first run and again only after its cadence elapses
- the trailing lookback window is passed to the executor with a NULL upper bound
- last-refreshed bookkeeping prevents redundant refreshes
- TimescaleUnavailable does not advance the schedule (it is retried)
- the default executor refuses unknown view names
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.workers import downsampler as ds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FakeExecutor:
    """Records (view, window_start, window_end) refresh calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, datetime | None, datetime | None]] = []

    async def __call__(self, view, window_start, window_end) -> None:
        self.calls.append((view, window_start, window_end))


def _now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# All three rollups are defined and refreshed (Req 6.6)
# ---------------------------------------------------------------------------
def test_default_aggregates_cover_5m_1h_1d():
    views = {spec.view for spec in ds.DEFAULT_AGGREGATES}
    assert views == {"telemetry_5m", "telemetry_1h", "telemetry_1d"}


async def test_first_run_refreshes_all_rollups():
    execute = FakeExecutor()
    last: dict[str, datetime] = {}

    refreshed = await ds.refresh_due_aggregates(
        execute, ds.DEFAULT_AGGREGATES, _now(), last
    )

    assert set(refreshed) == {"telemetry_5m", "telemetry_1h", "telemetry_1d"}
    assert {c[0] for c in execute.calls} == {
        "telemetry_5m",
        "telemetry_1h",
        "telemetry_1d",
    }


# ---------------------------------------------------------------------------
# Trailing window: lookback start, NULL (None) upper bound
# ---------------------------------------------------------------------------
async def test_refresh_uses_trailing_lookback_window_with_null_end():
    execute = FakeExecutor()
    now = _now()

    await ds.refresh_due_aggregates(execute, ds.DEFAULT_AGGREGATES, now, {})

    by_view = {c[0]: c for c in execute.calls}
    # 5m rollup -> trailing 1 hour; upper bound is None (refresh up to latest).
    assert by_view["telemetry_5m"][1] == now - timedelta(hours=1)
    assert by_view["telemetry_5m"][2] is None
    # 1h rollup -> trailing 1 day.
    assert by_view["telemetry_1h"][1] == now - timedelta(days=1)
    # 1d rollup -> trailing 7 days.
    assert by_view["telemetry_1d"][1] == now - timedelta(days=7)


# ---------------------------------------------------------------------------
# Cadence: not due again until cadence elapses
# ---------------------------------------------------------------------------
def test_due_aggregates_empty_when_within_cadence():
    now = _now()
    # Everything refreshed "just now".
    last = {spec.view: now for spec in ds.DEFAULT_AGGREGATES}

    # 3 minutes later: nothing is due (smallest cadence is 5 minutes).
    due = ds.due_aggregates(ds.DEFAULT_AGGREGATES, now + timedelta(minutes=3), last)
    assert due == []


def test_due_aggregates_only_the_5m_after_five_minutes():
    now = _now()
    last = {spec.view: now for spec in ds.DEFAULT_AGGREGATES}

    due = ds.due_aggregates(ds.DEFAULT_AGGREGATES, now + timedelta(minutes=5), last)
    assert [spec.view for spec in due] == ["telemetry_5m"]


def test_due_aggregates_all_after_a_day():
    now = _now()
    last = {spec.view: now for spec in ds.DEFAULT_AGGREGATES}

    due = ds.due_aggregates(ds.DEFAULT_AGGREGATES, now + timedelta(days=1), last)
    assert {spec.view for spec in due} == {
        "telemetry_5m",
        "telemetry_1h",
        "telemetry_1d",
    }


async def test_refresh_records_last_refreshed_and_skips_until_due():
    execute = FakeExecutor()
    now = _now()
    last: dict[str, datetime] = {}

    await ds.refresh_due_aggregates(execute, ds.DEFAULT_AGGREGATES, now, last)
    first_count = len(execute.calls)
    assert first_count == 3

    # 1 minute later nothing is due -> no new calls.
    await ds.refresh_due_aggregates(
        execute, ds.DEFAULT_AGGREGATES, now + timedelta(minutes=1), last
    )
    assert len(execute.calls) == first_count


# ---------------------------------------------------------------------------
# Availability failures do not advance the schedule
# ---------------------------------------------------------------------------
async def test_unavailable_executor_does_not_record_refresh():
    async def failing(view, start, end):
        raise ds.TimescaleUnavailable("connection refused")

    last: dict[str, datetime] = {}
    with pytest.raises(ds.TimescaleUnavailable):
        await ds.refresh_due_aggregates(failing, ds.DEFAULT_AGGREGATES, _now(), last)

    # The first (failing) view was never stamped, so it stays due for retry.
    assert last == {}


# ---------------------------------------------------------------------------
# Default executor guards against unknown view names
# ---------------------------------------------------------------------------
async def test_refresh_aggregate_rejects_unknown_view():
    with pytest.raises(ValueError):
        await ds.refresh_aggregate("telemetry_evil; DROP TABLE telemetry", None, None)


# ---------------------------------------------------------------------------
# Run loop stops promptly on shutdown
# ---------------------------------------------------------------------------
async def test_run_stops_when_event_set():
    import asyncio

    execute = FakeExecutor()
    stop = asyncio.Event()
    stop.set()  # already requested -> loop should exit without refreshing

    await ds.run(execute, stop_event=stop, poll_interval=0.01)

    assert execute.calls == []
