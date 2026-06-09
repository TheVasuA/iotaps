"""Property-based test for real-time latest-value publication (Task 5.4).

# Feature: iotaps-platform, Property 6: Real-time latest-value publication

Property 6 (design.md "Correctness Properties"):

    For any batch of written telemetry, the value published to the pub/sub
    channel for each device equals that device's record with the maximum
    timestamp in the batch.

Validates: Requirements 6.3, 6.4

The test drives the real :func:`app.workers.batch_writer.process_batch` with an
in-memory ``fakeredis`` queue and an injected fake insert, so no live Redis,
TimescaleDB, or MQTT broker is needed. For each generated batch it asserts that
after the commit:

- exactly one message is published per distinct device in the batch;
- each message goes to that device's telemetry channel; and
- the published record carries that device's maximum timestamp in the batch
  (with the payload matching one of the records sharing that max timestamp,
  since identical timestamps resolve last-write-wins).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core import redis_keys as rk
from app.workers import batch_writer as bw

# A fixed epoch the generated timestamp offsets are measured from.
_EPOCH = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# A small device-id pool so batches share devices and exercise the per-device
# latest-value selection rather than degenerating into one record per device.
_DEVICE_IDS = [f"dev-{i}" for i in range(5)]


def _iso(offset_seconds: int) -> str:
    """Render an ISO-8601 'Z' timestamp at ``offset_seconds`` past the epoch."""
    dt = _EPOCH + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# A single telemetry record: a device, a timestamp offset, and a value. Offsets
# range over a band small enough that ties (equal timestamps) occur, exercising
# the last-write-wins tie-break in latest_value_per_device.
_record = st.fixed_dictionaries(
    {
        "device_id": st.sampled_from(_DEVICE_IDS),
        "offset": st.integers(min_value=0, max_value=20),
        "value": st.floats(
            min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
        ),
    }
)


class _PublishCapture:
    """Transparent fakeredis proxy that records ``publish`` calls in order."""

    def __init__(self, redis):
        self._redis = redis
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel, message):
        self.messages.append((channel, message))
        return 0

    def __getattr__(self, name):
        return getattr(self._redis, name)


class _FakeInsert:
    """Fake idempotent insert: ON CONFLICT (device_id, ts) DO NOTHING."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}

    async def __call__(self, envelopes: list[dict]) -> None:
        for env in envelopes:
            self.store.setdefault((env["device_id"], env["ts"]), env)


async def _run(records: list[dict]) -> None:
    redis = _PublishCapture(fakeredis.aioredis.FakeRedis(decode_responses=True))
    insert = _FakeInsert()

    # Enqueue the generated batch in arrival order (RPUSH -> index 0 is first).
    for rec in records:
        envelope = json.dumps(
            {
                "org_id": "org-1",
                "device_id": rec["device_id"],
                "ts": _iso(rec["offset"]),
                "data": {"temp": rec["value"]},
            }
        )
        await redis.rpush(rk.INGEST_QUEUE, envelope)

    await bw.process_batch(redis, insert, batch_size=max(len(records), 1))

    # Expected latest offset per device = the maximum timestamp offset seen.
    expected_max_offset: dict[str, int] = {}
    for rec in records:
        dev = rec["device_id"]
        if dev not in expected_max_offset or rec["offset"] > expected_max_offset[dev]:
            expected_max_offset[dev] = rec["offset"]

    by_channel: dict[str, dict] = {}
    for channel, payload in redis.messages:
        # Exactly one publish per device: no channel published twice.
        assert channel not in by_channel, f"duplicate publish on {channel}"
        by_channel[channel] = json.loads(payload)

    # One message per distinct device, each on that device's telemetry channel.
    assert len(by_channel) == len(expected_max_offset)

    for dev, max_offset in expected_max_offset.items():
        channel = rk.telemetry_channel(dev)
        assert channel in by_channel, f"no publish for {dev}"
        published = by_channel[channel]
        assert published["device_id"] == dev
        # Property 6: the published record carries the device's max timestamp.
        assert published["ts"] == _iso(max_offset)
        # And its payload matches one of the records sharing that max timestamp.
        candidates = {
            rec["value"]
            for rec in records
            if rec["device_id"] == dev and rec["offset"] == max_offset
        }
        assert published["data"]["temp"] in candidates


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(records=st.lists(_record, min_size=1, max_size=30))
def test_real_time_latest_value_publication(records: list[dict]) -> None:
    """Property 6: real-time latest-value publication.

    Validates: Requirements 6.3, 6.4
    """
    asyncio.run(_run(records))
