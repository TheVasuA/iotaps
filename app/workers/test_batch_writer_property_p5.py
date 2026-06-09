"""Property-based test for telemetry batch write idempotency + completeness (Task 5.3).

# Feature: iotaps-platform, Property 5: Telemetry batch write idempotency and completeness

Property 5 (design.md "Correctness Properties"):

    For any queue of telemetry records (including duplicate ``(device_id, ts)``
    keys and redeliveries), processing the queue in batches of up to 1000 — and a
    larger batch when the backlog exceeds 1000 — results in the time-series store
    containing exactly the deduplicated set of records, with each record persisted
    exactly once regardless of retries.

Validates: Requirements 6.2, 6.9

The test drives the real :func:`app.workers.batch_writer.process_batch` with an
in-memory ``fakeredis`` queue and an injected fake idempotent insert, so no live
Redis, TimescaleDB, or MQTT broker is needed.

To exercise the *completeness regardless of retries* clause (Req 6.9) the fake
insert is made *flaky*: on a generated schedule it raises
:class:`TimescaleUnavailable`, which models the Time_Series_DB being down. When
that happens ``process_batch`` must leave the batch untrimmed in the queue (no
``LTRIM`` before commit), so the caller's retry loop re-processes it. The test
mimics that retry loop and asserts that after the queue finally drains:

- the store holds *exactly* the deduplicated set of ``(device_id, ts)`` keys
  present in the input (completeness: nothing dropped, even across retries);
- each key is persisted exactly once (idempotency: ``ON CONFLICT DO NOTHING``);
- the ingest queue is empty (every enqueued record was accounted for); and
- the persisted payload for each key is the first record seen for that key,
  matching ``ON CONFLICT (device_id, ts) DO NOTHING`` semantics.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core import redis_keys as rk
from app.workers import batch_writer as bw

# A fixed epoch the generated timestamp offsets are measured from.
_EPOCH = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# A small device-id pool so generated batches share devices and collide on
# timestamps, producing genuine duplicate ``(device_id, ts)`` keys.
_DEVICE_IDS = [f"dev-{i}" for i in range(4)]


def _iso(offset_seconds: int) -> str:
    """Render an ISO-8601 'Z' timestamp at ``offset_seconds`` past the epoch."""
    dt = _EPOCH + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# A single telemetry record. The narrow offset band guarantees frequent
# ``(device_id, ts)`` collisions so deduplication is actually exercised.
_record = st.fixed_dictionaries(
    {
        "device_id": st.sampled_from(_DEVICE_IDS),
        "offset": st.integers(min_value=0, max_value=8),
        "value": st.floats(
            min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
        ),
    }
)


class _FlakyIdempotentInsert:
    """Fake insert: idempotent (DO NOTHING) but periodically *unavailable*.

    ``fail_schedule`` is a queue of booleans consumed one per call. ``True``
    raises :class:`TimescaleUnavailable` *before* persisting anything (modelling
    a transaction that never commits), so the batch must be retained and retried
    by the caller (Req 6.9). ``False`` (or an exhausted schedule) commits the
    batch with ``ON CONFLICT (device_id, ts) DO NOTHING`` semantics.
    """

    def __init__(self, fail_schedule: list[bool]) -> None:
        self._schedule: deque[bool] = deque(fail_schedule)
        self.store: dict[tuple[str, str], dict] = {}

    async def __call__(self, envelopes: list[dict]) -> None:
        if self._schedule and self._schedule.popleft():
            raise bw.TimescaleUnavailable("simulated timescaledb outage")
        for env in envelopes:
            self.store.setdefault((env["device_id"], env["ts"]), env)


async def _run(records: list[dict], batch_size: int, fail_schedule: list[bool]) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    insert = _FlakyIdempotentInsert(fail_schedule)

    # Enqueue the generated batch in arrival order (RPUSH -> index 0 is first).
    # The first record seen for a given key is the one DO NOTHING keeps.
    first_seen: dict[tuple[str, str], dict] = {}
    for rec in records:
        ts = _iso(rec["offset"])
        envelope = {
            "org_id": "org-1",
            "device_id": rec["device_id"],
            "ts": ts,
            "data": {"temp": rec["value"]},
        }
        await redis.rpush(rk.INGEST_QUEUE, json.dumps(envelope))
        first_seen.setdefault((rec["device_id"], ts), envelope)

    # Drive the design's retry loop: retain-and-retry on TimescaleUnavailable
    # (Req 6.9), otherwise keep draining until the queue is empty. The bound is
    # generous but finite so a logic bug surfaces as a hang-free failure.
    max_iterations = len(records) * 4 + len(fail_schedule) + 50
    iterations = 0
    while await redis.llen(rk.INGEST_QUEUE) > 0:
        iterations += 1
        assert iterations <= max_iterations, "batch writer failed to drain the queue"
        try:
            await bw.process_batch(redis, insert, batch_size=batch_size)
        except bw.TimescaleUnavailable:
            # Batch retained for retry; the queue must not have shrunk/lost data.
            continue

    # Completeness: store holds exactly the deduplicated set of input keys, and
    # each key appears exactly once (a dict keyed by (device_id, ts) enforces the
    # "exactly once" cardinality; equality of the key sets enforces no loss and
    # no spurious rows).
    assert set(insert.store.keys()) == set(first_seen.keys())

    # Idempotency: ON CONFLICT DO NOTHING keeps the first record per key, so the
    # persisted payload matches the first envelope enqueued for that key even
    # though the batch may have been re-processed across retries.
    for key, envelope in first_seen.items():
        assert insert.store[key]["data"] == envelope["data"]

    # Every enqueued record was accounted for: LTRIM only runs after commit, so a
    # fully drained queue means nothing was dropped (Req 6.9).
    assert await redis.llen(rk.INGEST_QUEUE) == 0


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    records=st.lists(_record, min_size=1, max_size=40),
    # batch_size spans values below and above the batch length so both the
    # "batch of up to N" path and the "drain larger batch when backlog > N" path
    # (Req 6.2) are exercised.
    batch_size=st.integers(min_value=1, max_value=10),
    # A schedule of simulated TimescaleDB outages interleaved with successes so
    # the same batch is retried without data loss (Req 6.9).
    fail_schedule=st.lists(st.booleans(), max_size=12),
)
def test_telemetry_batch_write_idempotency_and_completeness(
    records: list[dict], batch_size: int, fail_schedule: list[bool]
) -> None:
    """Property 5: telemetry batch write idempotency and completeness.

    Validates: Requirements 6.2, 6.9
    """
    asyncio.run(_run(records, batch_size, fail_schedule))
