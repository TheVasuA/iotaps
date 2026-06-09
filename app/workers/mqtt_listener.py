"""MQTT_Listener worker (Req 6.1, 30.1).

The MQTT_Listener is the entry point of the telemetry ingestion pipeline
(design "Telemetry Ingestion Pipeline"). It connects to Mosquitto with the
backend's privileged credentials and subscribes to the cross-org wildcards:

    iotaps/+/+/telemetry   -> validated + LPUSHed onto the Redis ingest queue
    iotaps/+/+/status      -> device online/offline presence (LWT) tracking
    iotaps/+/+/ack         -> command acknowledgements (full handling in 9.x)

Design references:
- Topic layout ``iotaps/{org_id}/{device_id}/{type}`` (``app.core.mqtt_topics``).
- Ingest queue + presence set + pub/sub channels (``app.core.redis_keys``).
- Payload contracts (design "MQTT topics & payloads"):
    telemetry: {"ts": "<iso8601>", "data": {"<key>": <number>, ...}}
    status:    {"status": "online|offline", "ts": "<iso8601>"}
    ack:       {"command_id": "<uuid>", "result": "ok|error", "ts": "<iso8601>"}

This module keeps the parse/validate/handle logic as pure functions so it can
be unit-tested with fakeredis and without a live broker; the aiomqtt client
loop (``run``/``main``) wires those functions to real MQTT delivery and adds
graceful reconnect.

Scope note (Task 5.1): telemetry enqueue + presence tracking. The Batch_Writer
(5.2) drains the queue; the WebSocket gateway (5.5) consumes pub/sub. ACK
messages are forwarded to the device pub/sub channel here but full command
correlation lives in Task 9.x.
"""

from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.core import redis_keys as rk
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.mqtt_topics import (
    ALL_ACK_SUBSCRIPTION,
    ALL_STATUS_SUBSCRIPTION,
    ALL_TELEMETRY_SUBSCRIPTION,
    TOPIC_ROOT,
    MessageType,
)
from app.core.redis_client import get_redis
from app.services.quota_service import count_telemetry_message, resolve_org_plan

logger = get_logger(__name__)

# Seconds to wait before reconnecting after the broker connection drops.
RECONNECT_DELAY_SECONDS = 5

# Async callable that publishes a JSON command payload to an MQTT topic. Used to
# flush queued commands when a device reconnects (Req 9.6); injected so the
# handler can be unit-tested without a live broker.
CommandPublisher = Callable[[str, str], Awaitable[None]]

# Valid device status values carried on the status/LWT topic.
_ONLINE = "online"
_OFFLINE = "offline"


# ---------------------------------------------------------------------------
# Topic parsing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedTopic:
    """A decomposed ``iotaps/{org_id}/{device_id}/{type}`` topic."""

    org_id: str
    device_id: str
    message_type: MessageType


def parse_topic(topic: str) -> Optional[ParsedTopic]:
    """Parse a device topic into its parts, or ``None`` if it does not match.

    A topic is valid only when it has exactly four segments, the first is the
    ``iotaps`` root, the org/device segments are non-empty, and the final
    segment is a known :class:`MessageType`. Anything else (wrong root, extra
    segments, unknown type, empty ids) is rejected so malformed/untrusted
    topics never reach the queue (design "treat all MQTT payloads as untrusted").
    """
    if not topic:
        return None
    parts = topic.split("/")
    if len(parts) != 4:
        return None
    root, org_id, device_id, type_segment = parts
    if root != TOPIC_ROOT or not org_id or not device_id:
        return None
    try:
        message_type = MessageType(type_segment)
    except ValueError:
        return None
    return ParsedTopic(org_id=org_id, device_id=device_id, message_type=message_type)


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------
def _decode_json(payload: bytes | str) -> Optional[dict[str, Any]]:
    """Decode a JSON object payload, returning ``None`` if it is not valid.

    Only JSON objects are accepted; arrays, scalars, and malformed bytes are
    rejected.
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def validate_telemetry_payload(payload: bytes | str) -> Optional[dict[str, Any]]:
    """Validate a telemetry payload against the contract, or return ``None``.

    Contract: ``{"ts": "<iso8601>", "data": {"<key>": <number>, ...}}``.
    Requirements:
    - top-level JSON object
    - ``ts`` present and a non-empty string
    - ``data`` present, a non-empty object whose values are all numbers
      (bools are rejected since ``bool`` is a numeric subtype in Python)
    """
    obj = _decode_json(payload)
    if obj is None:
        return None

    ts = obj.get("ts")
    if not isinstance(ts, str) or not ts.strip():
        return None

    data = obj.get("data")
    if not isinstance(data, dict) or not data:
        return None
    for key, value in data.items():
        if not isinstance(key, str) or not key:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

    return obj


def validate_status_payload(payload: bytes | str) -> Optional[str]:
    """Validate a status/LWT payload, returning ``"online"``/``"offline"``.

    Contract: ``{"status": "online|offline", "ts": "..."}``. Returns ``None``
    for anything that is not one of the two recognised status values.
    """
    obj = _decode_json(payload)
    if obj is None:
        return None
    status = obj.get("status")
    if status in (_ONLINE, _OFFLINE):
        return status
    return None


# ---------------------------------------------------------------------------
# Message handling (pure side effects against Redis)
# ---------------------------------------------------------------------------
async def handle_telemetry(redis: Any, parsed: ParsedTopic, payload: bytes | str) -> bool:
    """Validate telemetry and LPUSH an envelope onto the ingest queue (Req 6.1).

    The enqueued envelope wraps the raw payload with the org/device ids parsed
    from the topic so the Batch_Writer (5.2) can persist without re-parsing
    topics. Returns ``True`` when a message was enqueued, ``False`` when the
    payload was rejected.
    """
    validated = validate_telemetry_payload(payload)
    if validated is None:
        logger.warning(
            "telemetry_rejected",
            extra={"org_id": parsed.org_id, "device_id": parsed.device_id},
        )
        return False

    envelope = {
        "org_id": parsed.org_id,
        "device_id": parsed.device_id,
        "ts": validated["ts"],
        "data": validated["data"],
    }
    await redis.lpush(rk.INGEST_QUEUE, json.dumps(envelope))

    # Count the message against the org's monthly Message_Quota (Req 15.3-15.6).
    # This only meters Free/ambiguous plans and never blocks ingestion: the
    # telemetry is already enqueued above, so a quota error cannot drop data.
    try:
        plan = await resolve_org_plan(redis, parsed.org_id)
        await count_telemetry_message(
            redis, parsed.org_id, plan, message_type=parsed.message_type
        )
    except Exception:  # pragma: no cover - quota bookkeeping must never lose data
        logger.warning(
            "quota_count_failed",
            extra={"org_id": parsed.org_id, "device_id": parsed.device_id},
        )
    return True


async def handle_status(
    redis: Any,
    parsed: ParsedTopic,
    payload: bytes | str,
    publisher: "Optional[CommandPublisher]" = None,
) -> Optional[str]:
    """Track device presence from a status/LWT message into ONLINE_DEVICES.

    ``online`` adds the device id to the set; ``offline`` removes it. The
    parsed device-scoped event is also published so the WebSocket gateway (5.5)
    can surface presence changes. When a device comes ``online`` and a
    ``publisher`` is supplied, any commands queued while it was offline are
    flushed and transitioned QUEUED -> SENT (Req 9.6). Returns the applied
    status or ``None`` when the payload was invalid.
    """
    status = validate_status_payload(payload)
    if status is None:
        logger.warning(
            "status_rejected",
            extra={"org_id": parsed.org_id, "device_id": parsed.device_id},
        )
        return None

    if status == _ONLINE:
        await redis.sadd(rk.ONLINE_DEVICES, parsed.device_id)
        if publisher is not None:
            # Flush commands queued while the device was offline (Req 9.6).
            try:
                from app.services.command_service import flush_queued_commands

                await flush_queued_commands(
                    redis, parsed.org_id, parsed.device_id, publisher
                )
            except Exception:  # pragma: no cover - flush must not break presence
                logger.exception(
                    "command_flush_failed",
                    extra={"org_id": parsed.org_id, "device_id": parsed.device_id},
                )
    else:
        await redis.srem(rk.ONLINE_DEVICES, parsed.device_id)

    await redis.publish(
        rk.device_channel(parsed.device_id),
        json.dumps({"type": "status", "device_id": parsed.device_id, "status": status}),
    )
    return status


async def handle_ack(redis: Any, parsed: ParsedTopic, payload: bytes | str) -> bool:
    """Handle a command ACK: correlate by command_id and confirm (Req 9.4).

    The ACK payload carries ``{"command_id": ..., "result": "ok|error", ...}``.
    A valid ACK transitions the referenced command SENT -> CONFIRMED via the
    command service (a no-op if it already timed out / was confirmed). The raw
    ACK is also forwarded onto the device pub/sub channel so it is not silently
    dropped.
    """
    obj = _decode_json(payload)
    if obj is None:
        logger.warning(
            "ack_rejected",
            extra={"org_id": parsed.org_id, "device_id": parsed.device_id},
        )
        return False

    command_id = obj.get("command_id")
    if isinstance(command_id, str) and command_id:
        try:
            from app.services.command_service import confirm_command

            await confirm_command(redis, command_id)
        except Exception:  # pragma: no cover - confirmation must not break relay
            logger.exception("command_confirm_failed", extra={"command_id": command_id})

    await redis.publish(
        rk.device_channel(parsed.device_id),
        json.dumps({"type": "ack", "device_id": parsed.device_id, "ack": obj}),
    )
    return True


async def dispatch(
    redis: Any,
    topic: str,
    payload: bytes | str,
    publisher: "Optional[CommandPublisher]" = None,
) -> None:
    """Route one delivered MQTT message to the right handler by topic type.

    Unparseable topics are dropped with a warning. This is the single funnel
    used by both the live client loop and the unit tests. ``publisher`` is used
    to flush queued commands on device reconnect (Req 9.6).
    """
    parsed = parse_topic(topic)
    if parsed is None:
        logger.warning("topic_unparseable", extra={"topic": topic})
        return

    if parsed.message_type is MessageType.TELEMETRY:
        await handle_telemetry(redis, parsed, payload)
    elif parsed.message_type is MessageType.STATUS:
        await handle_status(redis, parsed, payload, publisher)
    elif parsed.message_type is MessageType.ACK:
        await handle_ack(redis, parsed, payload)
    else:  # COMMAND is broker->device; the listener never receives it.
        logger.warning("unexpected_message_type", extra={"topic": topic})


# ---------------------------------------------------------------------------
# Live client loop
# ---------------------------------------------------------------------------
# Topics the backend listener subscribes to. COMMAND is intentionally absent
# (it flows broker -> device).
_SUBSCRIPTIONS = (
    ALL_TELEMETRY_SUBSCRIPTION,
    ALL_STATUS_SUBSCRIPTION,
    ALL_ACK_SUBSCRIPTION,
)


async def _run_once(stop_event: asyncio.Event) -> None:
    """Connect once, subscribe, and dispatch messages until disconnected.

    Raises ``aiomqtt.MqttError`` on connection loss so the outer ``run`` loop
    can reconnect.
    """
    import aiomqtt  # imported lazily so unit tests don't require the broker lib

    settings = get_settings()
    redis = get_redis()
    if redis is None:  # pragma: no cover - defensive; redis lib should be present
        raise RuntimeError("Redis client unavailable; cannot run MQTT_Listener")

    async with aiomqtt.Client(hostname=settings.mqtt_host, port=settings.mqtt_port) as client:
        for subscription in _SUBSCRIPTIONS:
            await client.subscribe(subscription)
        logger.info("mqtt_listener_subscribed", extra={"subscriptions": list(_SUBSCRIPTIONS)})

        async def _publish(topic: str, payload: str) -> None:
            await client.publish(topic, payload)

        async for message in client.messages:
            if stop_event.is_set():
                break
            try:
                await dispatch(redis, str(message.topic), message.payload, _publish)
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("message_dispatch_failed", extra={"topic": str(message.topic)})


async def run(stop_event: Optional[asyncio.Event] = None) -> None:
    """Run the listener with automatic reconnect until ``stop_event`` is set."""
    import aiomqtt

    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        try:
            await _run_once(stop_event)
        except aiomqtt.MqttError as exc:
            if stop_event.is_set():
                break
            logger.warning(
                "mqtt_connection_lost",
                extra={"error": str(exc), "retry_in_seconds": RECONNECT_DELAY_SECONDS},
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=RECONNECT_DELAY_SECONDS)
            except asyncio.TimeoutError:
                continue


def main() -> None:
    """Process entry point used by supervisor (``python -m app.workers.mqtt_listener``)."""
    configure_logging()
    logger.info("mqtt_listener_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # pragma: no cover - Windows lacks add_signal_handler
                pass
        await run(stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - graceful Ctrl-C on platforms w/o handler
        pass
    logger.info("mqtt_listener_stopped")


if __name__ == "__main__":
    main()
