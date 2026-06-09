"""End-to-end telemetry latency integration test (Task 5.6, Req 6.4).

Exercises the full real-time path the platform promises a dashboard client:

    enqueue telemetry  ->  Batch_Writer.process_batch (commit + publish)
                       ->  Redis pub/sub fan-out
                       ->  WebSocketSession.pump  ->  client receives < 1s

Req 6.4: "WHEN new telemetry for a Device is received, THE Platform SHALL
deliver the updated value to subscribed Dashboard clients via WebSocket within
1 second of ingestion."

Unlike the focused unit tests in ``test_ws.py`` (session bridge) and
``test_batch_writer.py`` (batch processing), this test wires both stages onto a
single in-memory ``fakeredis`` instance so no live Redis, TimescaleDB, MQTT
broker, or ASGI server is required. The Batch_Writer's TimescaleDB insert is
replaced with an in-memory fake (idempotent on ``(device_id, ts)``) so the test
measures the transport latency of the publish -> pub/sub -> WebSocket hop, which
is exactly what Req 6.4 bounds.

The elapsed time is measured from the moment ingestion is triggered
(``process_batch``, which commits then publishes the latest value per device,
Req 6.3) to the moment the subscribed client receives the telemetry frame, and
asserted to be strictly under 1.0 second.
"""

from __future__ import annotations

import asyncio
import json
import time

import fakeredis.aioredis

from app.api import ws
from app.core import redis_keys as rk
from app.core.security.principal import Principal
from app.workers import batch_writer as bw


# Req 6.4 latency budget for WebSocket delivery of new telemetry.
LATENCY_BUDGET_SECONDS = 1.0


class _FakeWebSocket:
    """Captures frames sent to the client and stamps the first arrival time."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.first_received_at: float | None = None

    async def send_text(self, text: str) -> None:
        if self.first_received_at is None:
            self.first_received_at = time.perf_counter()
        self.sent.append(text)


class _FakeInsert:
    """In-memory stand-in for the TimescaleDB write (idempotent upsert)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], dict] = {}

    async def __call__(self, envelopes: list[dict]) -> None:
        for env in envelopes:
            self.store.setdefault((env["device_id"], env["ts"]), env)


def _principal() -> Principal:
    return Principal(user_id="user-1", org_id="org-1", role="project_center")


def _envelope(device_id: str, ts: str, value: float, org_id: str = "org-1") -> str:
    return json.dumps(
        {"org_id": org_id, "device_id": device_id, "ts": ts, "data": {"temp": value}}
    )


async def _wait_for_delivery(sink: _FakeWebSocket, *, timeout: float) -> None:
    """Poll until the client receives a frame or the timeout elapses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while not sink.sent and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)


async def test_telemetry_reaches_subscribed_client_within_one_second():
    """Publishing telemetry delivers it to a subscribed WebSocket client < 1s.

    Validates Requirement 6.4.
    """
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    insert = _FakeInsert()
    sink = _FakeWebSocket()

    device_id = "dev-latency"
    ts = "2025-01-01T00:00:00Z"

    # A dashboard client opens a session and subscribes to the device channel.
    session = ws.WebSocketSession(sink.send_text, _principal(), redis)
    await session.subscribe([f"device:{device_id}"])

    # Start the bridge pump and let the pub/sub subscription register.
    pump = asyncio.create_task(session.pump())
    await asyncio.sleep(0.05)

    try:
        # A telemetry message is ingested onto the queue (as the MQTT_Listener
        # would), then the Batch_Writer commits it and publishes the latest
        # value. Timing starts at ingestion-trigger.
        await redis.rpush(rk.INGEST_QUEUE, _envelope(device_id, ts, 24.1))

        started_at = time.perf_counter()
        processed = await bw.process_batch(redis, insert)
        assert processed == 1

        await _wait_for_delivery(sink, timeout=LATENCY_BUDGET_SECONDS + 0.5)
    finally:
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        await session.close()

    # The client received exactly the published telemetry frame.
    assert len(sink.sent) == 1
    frame = json.loads(sink.sent[0])
    assert frame["type"] == "telemetry"
    assert frame["device_id"] == device_id
    assert frame["ts"] == ts
    assert frame["data"] == {"temp": 24.1}

    # End-to-end delivery latency is within the Req 6.4 budget (< 1s).
    assert sink.first_received_at is not None
    elapsed = sink.first_received_at - started_at
    assert elapsed < LATENCY_BUDGET_SECONDS, (
        f"telemetry delivery took {elapsed:.3f}s, exceeding the "
        f"{LATENCY_BUDGET_SECONDS}s budget (Req 6.4)"
    )


async def test_latest_value_delivered_within_budget_with_batch():
    """With a multi-record batch, the latest value reaches the client < 1s.

    Validates Requirement 6.4 (alongside 6.3 latest-value-per-device selection).
    """
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    insert = _FakeInsert()
    sink = _FakeWebSocket()

    device_id = "dev-batch"
    session = ws.WebSocketSession(sink.send_text, _principal(), redis)
    await session.subscribe([f"device:{device_id}"])
    pump = asyncio.create_task(session.pump())
    await asyncio.sleep(0.05)

    try:
        # Several records for one device; the newest (max ts) should be pushed.
        await redis.rpush(rk.INGEST_QUEUE, _envelope(device_id, "2025-01-01T00:00:00Z", 1.0))
        await redis.rpush(rk.INGEST_QUEUE, _envelope(device_id, "2025-01-01T00:00:05Z", 9.0))
        await redis.rpush(rk.INGEST_QUEUE, _envelope(device_id, "2025-01-01T00:00:02Z", 5.0))

        started_at = time.perf_counter()
        processed = await bw.process_batch(redis, insert)
        assert processed == 3

        await _wait_for_delivery(sink, timeout=LATENCY_BUDGET_SECONDS + 0.5)
    finally:
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        await session.close()

    assert len(sink.sent) == 1
    frame = json.loads(sink.sent[0])
    assert frame["ts"] == "2025-01-01T00:00:05Z"
    assert frame["data"] == {"temp": 9.0}

    assert sink.first_received_at is not None
    elapsed = sink.first_received_at - started_at
    assert elapsed < LATENCY_BUDGET_SECONDS, (
        f"telemetry delivery took {elapsed:.3f}s, exceeding the "
        f"{LATENCY_BUDGET_SECONDS}s budget (Req 6.4)"
    )
