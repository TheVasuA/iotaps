"""Batch_Writer worker (Req 6.2, 6.3, 6.9, 6.10, 30.1).

The Batch_Writer is the second stage of the telemetry ingestion pipeline
(design "Telemetry Ingestion Pipeline" / "Telemetry Batch Writer"). It drains
the Redis ingest queue that the MQTT_Listener (Task 5.1) fills, bulk-inserts the
records into the TimescaleDB ``telemetry`` hypertable idempotently, and then
publishes the latest value per device to the Redis pub/sub channels consumed by
the WebSocket gateway (Task 5.5).

Design references (design.md "Core Algorithms -> Telemetry Batch Writer"):

    loop forever:
        batch = redis.lrange(QUEUE, 0, BATCH_SIZE-1)      # BATCH_SIZE = 1000
        backlog = redis.llen(QUEUE)
        if backlog > BATCH_SIZE:
            batch = redis.lrange(QUEUE, 0, backlog-1)      # drain larger batch
        if batch empty: sleep(50ms); continue
        try:
            timescaledb.execute(INSERT ... ON CONFLICT (device_id, ts) DO NOTHING)
            redis.ltrim(QUEUE, len(batch), -1)             # remove only after commit
            for device, latest in last_value_per_device(batch):
                redis.publish("telemetry:"+device, latest)
        except TimescaleUnavailable:
            sleep(backoff); continue                       # keep batch, retry (6.9)
        except OtherWriteError:
            log_error(); fail_without_retry()              # 6.10

Key invariants enforced here:
- ``LTRIM`` runs *only after* a successful commit, so a crash or unavailable
  database never loses queued telemetry (the records stay at the head of the
  queue and are re-processed) (Req 6.9).
- Inserts use ``ON CONFLICT (device_id, ts) DO NOTHING`` so redeliveries and
  retries are idempotent (Req 6.2, Property 5).
- The value published per device is that device's record with the maximum
  timestamp in the batch (Req 6.3, Property 6).

The core (`process_batch`) takes the Redis client and an ``insert_fn`` callable
as parameters so it can be unit-tested with ``fakeredis`` and a fake insert,
without a live TimescaleDB. The ``main`` loop wires the real Redis client and
the asyncpg-backed insert together and adds graceful shutdown + backoff.
"""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from app.core import redis_keys as rk
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

# Largest batch drained when the backlog is at or below this size. When the
# backlog exceeds BATCH_SIZE the whole backlog is drained in one larger batch so
# the queue does not grow unbounded (Req 6.2).
BATCH_SIZE = 1000

# Idle poll interval — batch writer now runs every 60s for DB persistence.
# Real-time display is handled directly by the MQTT listener (no queue needed).
EMPTY_SLEEP_SECONDS = 60.0

# Exponential backoff bounds applied while TimescaleDB is unavailable (Req 6.9).
BACKOFF_INITIAL_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 30.0

# An insert callable persists a list of telemetry record dicts and commits.
InsertFn = Callable[[list[dict[str, Any]]], Awaitable[None]]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class BatchWriteError(Exception):
    """Base class for Batch_Writer persistence failures."""


class TimescaleUnavailable(BatchWriteError):
    """The Time_Series_DB could not be reached for the write (Req 6.9).

    Raised by an ``insert_fn`` when the failure is an availability/connection
    problem. The batch is retained in the queue and retried with backoff.
    """


# ---------------------------------------------------------------------------
# Envelope parsing + latest-value selection (pure helpers)
# ---------------------------------------------------------------------------
def _parse_envelope(raw: str | bytes) -> Optional[dict[str, Any]]:
    """Decode one queued telemetry envelope, or ``None`` if malformed.

    The MQTT_Listener enqueues envelopes shaped as::

        {"org_id": "...", "device_id": "...", "ts": "<iso8601>", "data": {...}}

    Anything that is not a JSON object carrying non-empty ``device_id``/``ts``
    and a ``data`` object is rejected so a single poison record cannot wedge the
    pipeline.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    device_id = obj.get("device_id")
    ts = obj.get("ts")
    data = obj.get("data")
    if not isinstance(device_id, str) or not device_id:
        return None
    if not isinstance(ts, str) or not ts.strip():
        return None
    if not isinstance(data, dict):
        return None
    return obj


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware ``datetime`` for comparison.

    A trailing ``Z`` (UTC) is normalised to ``+00:00``. Naive timestamps are
    assumed to be UTC. Unparseable timestamps sort as the epoch minimum so a
    valid record always wins the latest-value comparison over a garbled one.
    """
    text = ts.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def latest_value_per_device(
    envelopes: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return, per device, the envelope with the maximum timestamp (Req 6.3).

    Property 6: for each device the published value equals that device's record
    with the maximum timestamp in the batch. Ties (identical timestamps) resolve
    to the later occurrence in the batch, matching last-write-wins ordering.
    """
    latest: dict[str, dict[str, Any]] = {}
    latest_ts: dict[str, datetime] = {}
    for env in envelopes:
        device_id = env["device_id"]
        ts = _parse_ts(env["ts"])
        if device_id not in latest_ts or ts >= latest_ts[device_id]:
            latest[device_id] = env
            latest_ts[device_id] = ts
    return latest


# ---------------------------------------------------------------------------
# Core batch processing (testable; no live DB required)
# ---------------------------------------------------------------------------
async def process_batch(
    redis: Any,
    insert_fn: InsertFn,
    *,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Drain and persist one batch from the ingest queue. Returns rows handled.

    Steps (design "Telemetry Batch Writer"):
    1. ``LRANGE`` up to ``batch_size`` items; if the backlog (``LLEN``) exceeds
       ``batch_size`` drain the whole backlog in one larger batch (Req 6.2).
    2. ``insert_fn`` bulk-inserts idempotently and commits (Req 6.2).
    3. ``LTRIM`` removes exactly the processed items *only after* the commit
       succeeds, so nothing is lost on failure (Req 6.9).
    4. Publish the latest value per device to its pub/sub channel (Req 6.3).

    Returns the number of raw queue entries processed (0 when the queue was
    empty). On a write failure no ``LTRIM`` is performed and the exception
    propagates so the caller can apply the retry/backoff policy:
    :class:`TimescaleUnavailable` -> retain + retry (Req 6.9); any other
    exception -> fail without retry (Req 6.10).
    """
    raw_batch: list[str] = await redis.lrange(rk.INGEST_QUEUE, 0, batch_size - 1)
    backlog = await redis.llen(rk.INGEST_QUEUE)
    if backlog > batch_size:
        # Drain the whole backlog in a single larger batch to clear it (Req 6.2).
        raw_batch = await redis.lrange(rk.INGEST_QUEUE, 0, backlog - 1)

    if not raw_batch:
        return 0

    batch_len = len(raw_batch)

    envelopes: list[dict[str, Any]] = []
    for raw in raw_batch:
        env = _parse_envelope(raw)
        if env is None:
            logger.warning("telemetry_envelope_rejected")
            continue
        envelopes.append(env)

    # Persist + commit first. If this raises, the batch is left in the queue.
    if envelopes:
        await insert_fn(envelopes)

    # Commit succeeded (or the batch held only poison records): remove exactly
    # the entries we pulled. LTRIM keeps indices [batch_len, -1].
    await redis.ltrim(rk.INGEST_QUEUE, batch_len, -1)

    # Real-time pub/sub is handled by the MQTT listener directly now.
    # The batch writer only persists to DB for historical queries.

    return batch_len


# ---------------------------------------------------------------------------
# Default TimescaleDB insert (asyncpg / SQLAlchemy)
# ---------------------------------------------------------------------------
async def insert_telemetry(envelopes: list[dict[str, Any]]) -> None:
    """Bulk-insert telemetry into the hypertable idempotently (Req 6.2).

    Uses PostgreSQL ``INSERT ... ON CONFLICT (device_id, ts) DO NOTHING`` so
    duplicate ``(device_id, ts)`` keys from redeliveries or retries are silently
    ignored and each record is persisted exactly once (Property 5).

    Availability/connection failures are re-raised as :class:`TimescaleUnavailable`
    so the caller retains the batch and retries (Req 6.9); all other errors
    propagate unchanged so the caller fails without retrying (Req 6.10).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.exc import (
        DisconnectionError,
        InterfaceError,
        OperationalError,
    )

    from app.db.session import async_session_factory
    from app.models.telemetry import Telemetry

    rows = [
        {
            "org_id": env["org_id"],
            "device_id": env["device_id"],
            "ts": env["ts"],
            "data": env["data"],
        }
        for env in envelopes
    ]
    if not rows:
        return

    stmt = pg_insert(Telemetry).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["device_id", "ts"])

    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except (OperationalError, InterfaceError, DisconnectionError, ConnectionError, OSError) as exc:
        # Connection/availability problems: retain the batch and retry (Req 6.9).
        raise TimescaleUnavailable(str(exc)) from exc


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    redis: Any,
    insert_fn: InsertFn,
    stop_event: Optional[asyncio.Event] = None,
    *,
    batch_size: int = BATCH_SIZE,
) -> None:
    """Continuously drain the ingest queue until ``stop_event`` is set.

    Applies the design's retry policy around :func:`process_batch`:
    - empty queue -> short idle sleep then poll again;
    - :class:`TimescaleUnavailable` -> exponential backoff and retry, keeping the
      batch in the queue (Req 6.9);
    - any other write error -> log with context and stop without retrying the
      write (Req 6.10).
    """
    stop_event = stop_event or asyncio.Event()
    backoff = BACKOFF_INITIAL_SECONDS

    while not stop_event.is_set():
        try:
            processed = await process_batch(redis, insert_fn, batch_size=batch_size)
        except TimescaleUnavailable as exc:
            logger.warning(
                "timescaledb_unavailable_retrying",
                extra={"error": str(exc), "retry_in_seconds": backoff},
            )
            await _sleep_or_stop(stop_event, backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_SECONDS)
            continue
        except Exception as exc:
            # Non-availability write failure: fail without retrying (Req 6.10).
            logger.exception("batch_write_failed_no_retry", extra={"error": str(exc)})
            raise

        # Successful poll: reset backoff and idle briefly if the queue was empty.
        backoff = BACKOFF_INITIAL_SECONDS
        if processed == 0:
            # While idle, process any pending datastream discoveries
            await _process_datastream_discoveries(redis)
            await _sleep_or_stop(stop_event, EMPTY_SLEEP_SECONDS)


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _process_datastream_discoveries(redis: Any) -> None:
    """Register newly discovered telemetry keys as DeviceSensor entries.

    Drains up to 50 items from the discovery queue per cycle. Idempotent:
    skips keys that already exist in the DB.
    """
    import json as _json
    import uuid as _uuid

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.device import DeviceSensor

    for _ in range(50):
        raw = await redis.rpop("iotaps:datastream_discovery")
        if raw is None:
            break
        try:
            item = _json.loads(raw)
            device_id = _uuid.UUID(item["device_id"])
            key = item["key"]
        except Exception:
            continue

        try:
            async with async_session_factory() as session:
                # Check if already exists
                existing = await session.execute(
                    select(DeviceSensor).where(
                        DeviceSensor.device_id == device_id,
                        DeviceSensor.key == key,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue

                # Infer pin_type from key name
                pin_type = "sensor"
                if key.startswith("led") or key in ("relay", "switch", "motor", "fan", "pump"):
                    pin_type = "toggle"
                elif key in ("brightness", "speed", "volume", "angle", "pwm"):
                    pin_type = "slider"

                sensor = DeviceSensor(
                    device_id=device_id,
                    org_id=None,  # will be set below
                    key=key,
                    pin_type=pin_type,
                    display_name=key.replace("_", " ").title(),
                )
                # Get device org_id
                from app.models.device import Device
                device = await session.get(Device, device_id)
                if device:
                    sensor.org_id = device.org_id
                    session.add(sensor)
                    await session.commit()
                    logger.info("datastream_discovered", extra={"device_id": str(device_id), "key": key, "pin_type": pin_type})
        except Exception:
            logger.debug("datastream_discovery_skip", extra={"key": key})


def main() -> None:
    """Process entry point (``python -m app.workers.batch_writer``)."""
    configure_logging()
    logger.info("batch_writer_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        redis = get_redis()
        if redis is None:  # pragma: no cover - defensive; redis lib should be present
            raise RuntimeError("Redis client unavailable; cannot run Batch_Writer")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # pragma: no cover - Windows lacks add_signal_handler
                pass
        await run(redis, insert_telemetry, stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - graceful Ctrl-C
        pass
    logger.info("batch_writer_stopped")


if __name__ == "__main__":
    main()
