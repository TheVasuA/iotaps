"""Unit tests for the Batch_Writer worker (Task 5.2, Req 6.2, 6.3, 6.9, 6.10).

These cover the core batch-processing contract with ``fakeredis`` and an
injected fake insert function, so no live TimescaleDB or MQTT broker is needed:

- idempotent bulk insert (ON CONFLICT semantics simulated by the fake store)
- backlog draining (a larger batch when backlog > batch_size)
- LTRIM only after a successful commit (and never on failure)
- latest-value-per-device publication after commit
- retain-and-retry on TimescaleUnavailable; fail-without-retry on other errors
"""

from __future__ import annotations

import json

import fakeredis.aioredis
import pytest

from app.core import redis_keys as rk
from app.workers import batch_writer as bw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _redis() -> "fakeredis.aioredis.FakeRedis":
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _envelope(device_id: str, ts: str, value: float = 1.0, org_id: str = "org-1") -> str:
    return json.dumps(
        {"org_id": org_id, "device_id": device_id, "ts": ts, "data": {"temp": value}}
    )


async def _enqueue(redis, *envelopes: str) -> None:
    """Mimic the MQTT_Listener: LPUSH so the oldest record sits at the tail.

    LRANGE(0, n) returns newest-first; the worker treats the whole range as the
    batch, so head/tail ordering only matters for which records get trimmed.
    Here we RPUSH in arrival order to keep tests easy to reason about (index 0
    is the first arrival), which is consistent with the LTRIM(batch_len, -1)
    contract regardless of direction.
    """
    for env in envelopes:
        await redis.rpush(rk.INGEST_QUEUE, env)


class FakeInsert:
    """Records inserted rows with ON CONFLICT (device_id, ts) DO NOTHING."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}
        self.calls: list[list[dict]] = []

    async def __call__(self, envelopes: list[dict]) -> None:
        self.calls.append(envelopes)
        for env in envelopes:
            key = (env["device_id"], env["ts"])
            self.store.setdefault(key, env)  # DO NOTHING on conflict


# ---------------------------------------------------------------------------
# Idempotency (Req 6.2, Property 5)
# ---------------------------------------------------------------------------
async def test_duplicates_and_redeliveries_persist_once():
    redis = _redis()
    insert = FakeInsert()
    # Same (device, ts) appears three times across the queue.
    await _enqueue(
        redis,
        _envelope("dev-a", "2025-01-01T00:00:00Z", 1.0),
        _envelope("dev-a", "2025-01-01T00:00:00Z", 1.0),
        _envelope("dev-b", "2025-01-01T00:00:01Z", 2.0),
        _envelope("dev-a", "2025-01-01T00:00:00Z", 1.0),
    )

    processed = await bw.process_batch(redis, insert)

    assert processed == 4  # all four raw entries handled
    # Deduplicated store holds exactly the two distinct keys.
    assert set(insert.store.keys()) == {
        ("dev-a", "2025-01-01T00:00:00Z"),
        ("dev-b", "2025-01-01T00:00:01Z"),
    }


async def test_reprocessing_same_batch_is_idempotent():
    redis = _redis()
    insert = FakeInsert()
    await _enqueue(redis, _envelope("dev-a", "2025-01-01T00:00:00Z"))

    await bw.process_batch(redis, insert)
    # Re-enqueue the identical record (a redelivery) and process again.
    await _enqueue(redis, _envelope("dev-a", "2025-01-01T00:00:00Z"))
    await bw.process_batch(redis, insert)

    assert list(insert.store.keys()) == [("dev-a", "2025-01-01T00:00:00Z")]


# ---------------------------------------------------------------------------
# Backlog draining (Req 6.2)
# ---------------------------------------------------------------------------
async def test_processes_all_when_backlog_within_limit():
    redis = _redis()
    insert = FakeInsert()
    # 3 records, batch_size 5 -> backlog within limit, all processed, none left.
    for i in range(3):
        await _enqueue(redis, _envelope("dev-a", f"2025-01-01T00:00:0{i}Z", i))

    processed = await bw.process_batch(redis, insert, batch_size=5)

    assert processed == 3
    assert await redis.llen(rk.INGEST_QUEUE) == 0


async def test_drains_larger_batch_when_backlog_exceeds_batch_size():
    redis = _redis()
    insert = FakeInsert()
    # 7 records, batch_size 3 -> backlog (7) > 3, so the whole backlog drains.
    for i in range(7):
        await _enqueue(redis, _envelope(f"dev-{i}", f"2025-01-01T00:00:0{i}Z", i))

    processed = await bw.process_batch(redis, insert, batch_size=3)

    assert processed == 7
    assert await redis.llen(rk.INGEST_QUEUE) == 0


# ---------------------------------------------------------------------------
# LTRIM only after commit (Req 6.9)
# ---------------------------------------------------------------------------
async def test_ltrim_removes_processed_entries_after_commit():
    redis = _redis()
    insert = FakeInsert()
    await _enqueue(
        redis,
        _envelope("dev-a", "2025-01-01T00:00:00Z"),
        _envelope("dev-b", "2025-01-01T00:00:01Z"),
    )

    await bw.process_batch(redis, insert)

    assert await redis.llen(rk.INGEST_QUEUE) == 0


async def test_batch_retained_when_timescale_unavailable():
    redis = _redis()
    await _enqueue(
        redis,
        _envelope("dev-a", "2025-01-01T00:00:00Z"),
        _envelope("dev-b", "2025-01-01T00:00:01Z"),
    )

    async def failing_insert(_envelopes):
        raise bw.TimescaleUnavailable("connection refused")

    with pytest.raises(bw.TimescaleUnavailable):
        await bw.process_batch(redis, failing_insert)

    # Nothing was trimmed: the batch stays in the queue for retry (Req 6.9).
    assert await redis.llen(rk.INGEST_QUEUE) == 2


async def test_batch_retained_on_other_write_error():
    redis = _redis()
    await _enqueue(redis, _envelope("dev-a", "2025-01-01T00:00:00Z"))

    async def failing_insert(_envelopes):
        raise ValueError("bad column")

    with pytest.raises(ValueError):
        await bw.process_batch(redis, failing_insert)

    # The write failed before LTRIM, so the record is preserved (Req 6.10 callers
    # stop retrying, but data is never dropped by process_batch itself).
    assert await redis.llen(rk.INGEST_QUEUE) == 1


# ---------------------------------------------------------------------------
# Latest-value publication (Req 6.3, Property 6)
# ---------------------------------------------------------------------------
async def test_publishes_latest_value_per_device_after_commit():
    redis = _redis()
    insert = FakeInsert()
    published = PublishCapture(redis)

    await _enqueue(
        published,
        _envelope("dev-a", "2025-01-01T00:00:00Z", 1.0),
        _envelope("dev-a", "2025-01-01T00:00:05Z", 9.0),  # newest for dev-a
        _envelope("dev-a", "2025-01-01T00:00:02Z", 5.0),
        _envelope("dev-b", "2025-01-01T00:00:01Z", 2.0),
    )

    await bw.process_batch(published, insert)

    by_channel = {ch: json.loads(payload) for ch, payload in published.messages}

    # One publish per device, carrying that device's max-ts record (Property 6).
    assert by_channel[rk.telemetry_channel("dev-a")]["data"] == {"temp": 9.0}
    assert by_channel[rk.telemetry_channel("dev-a")]["ts"] == "2025-01-01T00:00:05Z"
    assert by_channel[rk.telemetry_channel("dev-b")]["data"] == {"temp": 2.0}
    assert len(published.messages) == 2


def test_latest_value_per_device_picks_max_ts():
    envelopes = [
        {"device_id": "d1", "ts": "2025-01-01T00:00:00Z", "data": {"v": 1}},
        {"device_id": "d1", "ts": "2025-01-01T00:00:10Z", "data": {"v": 2}},
        {"device_id": "d2", "ts": "2025-01-01T00:00:05Z", "data": {"v": 3}},
    ]
    latest = bw.latest_value_per_device(envelopes)
    assert latest["d1"]["data"] == {"v": 2}
    assert latest["d2"]["data"] == {"v": 3}


# ---------------------------------------------------------------------------
# Empty queue
# ---------------------------------------------------------------------------
async def test_empty_queue_returns_zero():
    redis = _redis()
    insert = FakeInsert()
    processed = await bw.process_batch(redis, insert)
    assert processed == 0
    assert insert.calls == []


# ---------------------------------------------------------------------------
# Malformed records do not wedge the pipeline
# ---------------------------------------------------------------------------
async def test_malformed_records_are_dropped_but_trimmed():
    redis = _redis()
    insert = FakeInsert()
    await redis.rpush(rk.INGEST_QUEUE, "not json")
    await _enqueue(redis, _envelope("dev-a", "2025-01-01T00:00:00Z"))

    processed = await bw.process_batch(redis, insert)

    assert processed == 2
    assert ("dev-a", "2025-01-01T00:00:00Z") in insert.store
    assert await redis.llen(rk.INGEST_QUEUE) == 0


# ---------------------------------------------------------------------------
# pubsub helpers
# ---------------------------------------------------------------------------
class PublishCapture:
    """Transparent Redis proxy that records ``publish`` calls deterministically.

    Delegates list/queue ops to the wrapped fakeredis client but captures
    ``(channel, message)`` tuples so the test can assert on what was published
    without relying on async pub/sub delivery timing.
    """

    def __init__(self, redis):
        self._redis = redis
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel, message):
        self.messages.append((channel, message))
        return 0

    def __getattr__(self, name):
        return getattr(self._redis, name)
