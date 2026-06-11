"""Device command service: issue, offline-queue, ACK, and timeout handling.

Implements the device-control flow from design.md ("Command Flow (with offline
queue + ACK)" and "Command Offline Queue + ACK Timeout") behind the Commands
API (Task 9.1, Req 9.1-9.7):

    POST /devices/{id}/commands       -> issue (publish when online, queue when offline)
    GET  /devices/{id}/commands/{cid} -> command status
    POST /devices/{id}/schedules      -> schedule/timer for a future command

Command lifecycle (Property 15 - "command status follows a valid state
machine"):

    issue while online   -> SENT       (published to MQTT command topic, ACK timer armed)
    issue while offline  -> QUEUED      (RPUSH cmdq:{device}; reject if the queue op fails)
    SENT + ACK           -> CONFIRMED   (device acknowledged, Req 9.4)
    SENT + ACK timeout   -> UNACKNOWLEDGED (Req 9.7)
    QUEUED + reconnect   -> SENT        (flush queued commands on reconnect, Req 9.6)

State is kept in Redis: per-command status records at ``cmd:{command_id}`` and
the offline queue at ``cmdq:{device}``. Command/ack/status messages are excluded
from the Free_Plan Message_Quota (Req 15.4), so this path never touches the
quota counter.

The transition rules are exposed as the pure :func:`next_status` /
:data:`LEGAL_TRANSITIONS` helpers so they can be reused by the command-status
state-machine property test (Task 9.2) and the ACK/timeout/flush helpers below
without duplicating the rules.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from app.core import redis_keys as rk
from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.mqtt_topics import command_topic, token_command_topic
from app.core.security.tenant import TenantScope
from app.models.device import Device
from app.models.ops import ActivityLog

logger = get_logger(__name__)

# Async callable that publishes ``payload`` (already JSON-encoded) to an MQTT
# topic. Injected so the service can be unit-tested without a live broker.
Publisher = Callable[[str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Command status state machine (Property 15, Req 9.4-9.7)
# ---------------------------------------------------------------------------
class CommandStatus(str, Enum):
    """The four legal command statuses (design "Commands")."""

    SENT = "SENT"
    QUEUED = "QUEUED"
    CONFIRMED = "CONFIRMED"
    UNACKNOWLEDGED = "UNACKNOWLEDGED"


# Terminal statuses never transition further.
TERMINAL_STATUSES: frozenset[CommandStatus] = frozenset(
    {CommandStatus.CONFIRMED, CommandStatus.UNACKNOWLEDGED}
)


class CommandEvent(str, Enum):
    """Events that can drive a command's status."""

    ISSUE_ONLINE = "issue_online"
    ISSUE_OFFLINE = "issue_offline"
    ACK = "ack"
    TIMEOUT = "timeout"
    RECONNECT_FLUSH = "reconnect_flush"


# The complete set of legal transitions. ``None`` as the source means "command
# does not yet exist" (initial issue). Any (status, event) pair not present here
# is illegal and :func:`next_status` returns ``None`` for it.
LEGAL_TRANSITIONS: dict[tuple[Optional[CommandStatus], CommandEvent], CommandStatus] = {
    (None, CommandEvent.ISSUE_ONLINE): CommandStatus.SENT,
    (None, CommandEvent.ISSUE_OFFLINE): CommandStatus.QUEUED,
    (CommandStatus.QUEUED, CommandEvent.RECONNECT_FLUSH): CommandStatus.SENT,
    (CommandStatus.SENT, CommandEvent.ACK): CommandStatus.CONFIRMED,
    (CommandStatus.SENT, CommandEvent.TIMEOUT): CommandStatus.UNACKNOWLEDGED,
}


def next_status(
    current: Optional[CommandStatus], event: CommandEvent
) -> Optional[CommandStatus]:
    """Return the status after applying ``event`` to ``current``.

    Returns ``None`` when the (status, event) pair is not a legal transition,
    so callers can treat illegal/duplicate events as no-ops (e.g. a late ACK
    after a timeout, a second ACK after confirmation). This is the single source
    of truth shared by the service and the Property 15 state-machine test.
    """
    return LEGAL_TRANSITIONS.get((current, event))


# ---------------------------------------------------------------------------
# Command payloads
# ---------------------------------------------------------------------------
_COMMAND_TYPES = frozenset({"on", "off", "value"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CommandRecord:
    """A command's stored status record (mirrors the ``cmd:{id}`` Redis value)."""

    command_id: str
    device_id: str
    org_id: str
    type: str
    value: Optional[float]
    status: CommandStatus
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "device_id": self.device_id,
            "org_id": self.org_id,
            "type": self.type,
            "value": self.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CommandRecord":
        return cls(
            command_id=raw["command_id"],
            device_id=raw["device_id"],
            org_id=raw["org_id"],
            type=raw["type"],
            value=raw.get("value"),
            status=CommandStatus(raw["status"]),
            created_at=raw["created_at"],
            updated_at=raw.get("updated_at", raw["created_at"]),
        )


def _command_mqtt_payload(record: CommandRecord) -> str:
    """Build the MQTT command payload published to the device (design contract).

    ``iotaps/{org}/{dev}/command  {"command_id": ..., "type": ..., "value": ...}``
    """
    body: dict[str, Any] = {"command_id": record.command_id, "type": record.type}
    if record.value is not None:
        body["value"] = record.value
    return json.dumps(body)


# ---------------------------------------------------------------------------
# Redis status-record persistence helpers (module-level so the ACK handler,
# timeout handler, and reconnect flush can be reused outside the request scope)
# ---------------------------------------------------------------------------
async def _load_record(redis: Any, command_id: str) -> Optional[CommandRecord]:
    raw = await redis.get(rk.command_record_key(command_id))
    if raw is None:
        return None
    return CommandRecord.from_dict(json.loads(raw))


async def _save_record(redis: Any, record: CommandRecord) -> None:
    await redis.set(rk.command_record_key(record.command_id), json.dumps(record.to_dict()))


def _with_status(record: CommandRecord, status: CommandStatus) -> CommandRecord:
    return CommandRecord(
        command_id=record.command_id,
        device_id=record.device_id,
        org_id=record.org_id,
        type=record.type,
        value=record.value,
        status=status,
        created_at=record.created_at,
        updated_at=_now_iso(),
    )


async def _publish_status_event(redis: Any, record: CommandRecord) -> None:
    """Publish a ``command_status`` event to the device channel (Req 6.4/7.4)."""
    try:
        await redis.publish(
            rk.device_channel(record.device_id),
            json.dumps(
                {
                    "type": "command_status",
                    "command_id": record.command_id,
                    "status": record.status.value,
                }
            ),
        )
    except Exception:  # pragma: no cover - status fan-out must not break the flow
        logger.exception("command_status_publish_failed", extra={"command_id": record.command_id})


# ---------------------------------------------------------------------------
# ACK / timeout / reconnect handlers (worker-side, Req 9.4, 9.6, 9.7)
# ---------------------------------------------------------------------------
async def confirm_command(redis: Any, command_id: str) -> Optional[CommandRecord]:
    """Handle a Command_ACK: SENT -> CONFIRMED (Req 9.4).

    Returns the updated record, or ``None`` when the command is unknown or the
    ACK is not a legal transition (e.g. it already timed out / was confirmed),
    in which case the ACK is ignored.
    """
    record = await _load_record(redis, command_id)
    if record is None:
        return None
    new = next_status(record.status, CommandEvent.ACK)
    if new is None:
        return None
    updated = _with_status(record, new)
    await _save_record(redis, updated)
    await _publish_status_event(redis, updated)
    return updated


async def expire_command(redis: Any, command_id: str) -> Optional[CommandRecord]:
    """Handle an ACK timeout: SENT -> UNACKNOWLEDGED (Req 9.7).

    A no-op (returns ``None``) when the command already left the SENT state
    (e.g. an ACK arrived first), so a CONFIRMED command is never downgraded.
    """
    record = await _load_record(redis, command_id)
    if record is None:
        return None
    new = next_status(record.status, CommandEvent.TIMEOUT)
    if new is None:
        return None
    updated = _with_status(record, new)
    await _save_record(redis, updated)
    await _publish_status_event(redis, updated)
    return updated


# Background ACK-timeout tasks are tracked here so they are not garbage
# collected before they fire (asyncio holds only weak references to tasks).
_ack_timers: "set[Any]" = set()


def schedule_ack_timeout(
    redis: Any, command_id: str, timeout_seconds: float
) -> None:
    """Arm a background timer that expires a command after ``timeout_seconds``.

    Spawns an asyncio task that sleeps then transitions the command
    SENT -> UNACKNOWLEDGED via :func:`expire_command` (a no-op if it was
    acknowledged first). Used by the online-issue path so a missing ACK is
    eventually reflected (Req 9.7). Requires a running event loop; callers
    without one (or with ``timeout_seconds <= 0``) should skip arming.
    """
    import asyncio

    async def _timer() -> None:
        try:
            await asyncio.sleep(timeout_seconds)
            await expire_command(redis, command_id)
        except asyncio.CancelledError:  # pragma: no cover - shutdown
            raise
        except Exception:  # pragma: no cover - timer must not crash the loop
            logger.exception("ack_timeout_failed", extra={"command_id": command_id})

    task = asyncio.ensure_future(_timer())
    _ack_timers.add(task)
    task.add_done_callback(_ack_timers.discard)


async def flush_queued_commands(
    redis: Any, org_id: str, device_id: str, publisher: Publisher
) -> list[CommandRecord]:
    """Flush a reconnected device's queued commands: QUEUED -> SENT (Req 9.6).

    Pops each queued command (FIFO via ``LPOP`` against the ``RPUSH``-filled
    queue), publishes it to the device's MQTT command topic, and transitions its
    status record to SENT. Returns the flushed records in delivery order.
    """
    # device_id here is the token (from the 3-segment topic). Use token-based topic.
    topic = token_command_topic(device_id)
    flushed: list[CommandRecord] = []

    # Resolve the device UUID for the queue key (queued by UUID)
    queue_device_id = device_id
    try:
        from app.db.session import async_session_factory
        from app.models.device import MqttCredential
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(
                select(MqttCredential.device_id).where(
                    MqttCredential.token == device_id,
                    MqttCredential.revoked == False,
                )
            )
            row = result.first()
            if row:
                queue_device_id = str(row[0])
    except Exception:
        pass

    queue_key = rk.command_queue_key(queue_device_id)
    while True:
        raw = await redis.lpop(queue_key)
        if raw is None:
            break
        queued = json.loads(raw)
        command_id = queued["command_id"]
        record = await _load_record(redis, command_id)
        if record is None:
            continue
        new = next_status(record.status, CommandEvent.RECONNECT_FLUSH)
        if new is None:
            # Not in QUEUED state (e.g. already handled); skip without delivery.
            continue
        updated = _with_status(record, new)
        await publisher(topic, _command_mqtt_payload(updated))
        await _save_record(redis, updated)
        await _publish_status_event(redis, updated)
        flushed.append(updated)
    return flushed


# ---------------------------------------------------------------------------
# Request-scoped command service
# ---------------------------------------------------------------------------
class CommandService:
    """Tenant-scoped command issue/query backed by Redis + an MQTT publisher."""

    def __init__(self, scope: TenantScope, redis: Any, publisher: Publisher) -> None:
        self._scope = scope
        self._session = scope.session
        self._redis = redis
        self._publisher = publisher

    async def _get_device(self, device_id: uuid.UUID) -> Device:
        return await self._scope.get(Device, device_id)

    def _log_command(self, device: Device, record: CommandRecord) -> None:
        """Write a ``device.command`` activity-log entry (Req 5.8)."""
        try:
            user_uuid = uuid.UUID(str(self._scope.principal.user_id))
        except (ValueError, TypeError):
            user_uuid = None
        self._session.add(
            ActivityLog(
                org_id=device.org_id,
                user_id=user_uuid,
                device_id=device.id,
                action="device.command",
                detail={
                    "command_id": record.command_id,
                    "type": record.type,
                    "value": record.value,
                    "status": record.status.value,
                },
            )
        )

    async def issue_command(
        self,
        device_id: uuid.UUID,
        *,
        type: str,
        value: Optional[float] = None,
        ack_timeout_seconds: int = 0,
    ) -> CommandRecord:
        """Issue a command: publish when online (SENT), queue when offline (QUEUED).

        Raises :class:`ValidationError` for an unknown command type or a
        ``value`` command missing its value, and :class:`CommandQueueError` when
        the offline queue operation fails (Req 9.5 reject-on-queue-failure).
        """
        if type not in _COMMAND_TYPES:
            raise ValidationError(
                f"Unknown command type '{type}'", error_code="invalid_command_type"
            )
        if type == "value" and value is None:
            raise ValidationError(
                "A 'value' command requires a value", error_code="missing_command_value"
            )
        if type != "value":
            value = None

        device = await self._get_device(device_id)

        command_id = str(uuid.uuid4())
        online = await self._redis.sismember(rk.ONLINE_DEVICES, str(device.id))
        event = CommandEvent.ISSUE_ONLINE if online else CommandEvent.ISSUE_OFFLINE
        status = next_status(None, event)
        assert status is not None  # issue events are always legal from None

        now = _now_iso()
        record = CommandRecord(
            command_id=command_id,
            device_id=str(device.id),
            org_id=str(device.org_id),
            type=type,
            value=value,
            status=status,
            created_at=now,
            updated_at=now,
        )

        if online:
            # Publish first; persist + log only once delivery to the broker
            # succeeded so a publish failure does not leave a phantom SENT.
            # Use token-based topic: iotaps/{token}/command (matches firmware)
            from app.models.device import MqttCredential
            from sqlalchemy import select

            cred_result = await self._session.execute(
                select(MqttCredential.token).where(
                    MqttCredential.device_id == device.id,
                    MqttCredential.revoked == False,
                )
            )
            cred_row = cred_result.first()
            if cred_row:
                topic = token_command_topic(cred_row[0])
            else:
                topic = command_topic(str(device.org_id), str(device.id))
            await self._publisher(topic, _command_mqtt_payload(record))
            await _save_record(self._redis, record)
            if ack_timeout_seconds > 0:
                # Arm an ACK timer so a missing ACK flips SENT -> UNACKNOWLEDGED
                # (Req 9.7). The timer is a no-op once an ACK confirms it.
                schedule_ack_timeout(self._redis, command_id, ack_timeout_seconds)
        else:
            # Offline: RPUSH onto the device queue; reject on failure (Req 9.5).
            queued_payload = json.dumps(
                {"command_id": command_id, "type": type, "value": value}
            )
            try:
                ok = await self._redis.rpush(
                    rk.command_queue_key(str(device.id)), queued_payload
                )
            except Exception as exc:  # pragma: no cover - defensive
                raise CommandQueueError(
                    "Failed to queue command for offline device"
                ) from exc
            if not ok:
                raise CommandQueueError("Failed to queue command for offline device")
            await _save_record(self._redis, record)

        await _publish_status_event(self._redis, record)

        self._log_command(device, record)
        await self._session.commit()
        return record

    async def get_command(
        self, device_id: uuid.UUID, command_id: str
    ) -> CommandRecord:
        """Return a command's status, enforcing device ownership (Req 3.3)."""
        device = await self._get_device(device_id)
        record = await _load_record(self._redis, command_id)
        if record is None or record.device_id != str(device.id):
            raise NotFoundError(
                "Command not found", error_code="command_not_found"
            )
        return record

    async def create_schedule(
        self,
        device_id: uuid.UUID,
        *,
        cron: str,
        type: str,
        value: Optional[float] = None,
    ) -> dict[str, Any]:
        """Create a schedule/timer that runs a command at the scheduled time (Req 9.3).

        Persists the schedule definition in the device's schedule list so a
        scheduler worker can execute the associated command when due. Returns
        the stored schedule definition.
        """
        if type not in _COMMAND_TYPES:
            raise ValidationError(
                f"Unknown command type '{type}'", error_code="invalid_command_type"
            )
        if type == "value" and value is None:
            raise ValidationError(
                "A 'value' command requires a value", error_code="missing_command_value"
            )
        if not cron or not cron.strip():
            raise ValidationError("A schedule cron is required", error_code="invalid_cron")

        device = await self._get_device(device_id)
        schedule = {
            "schedule_id": str(uuid.uuid4()),
            "device_id": str(device.id),
            "org_id": str(device.org_id),
            "cron": cron.strip(),
            "command": {"type": type, "value": value if type == "value" else None},
            "created_at": _now_iso(),
        }
        await self._redis.rpush(
            rk.command_schedule_key(str(device.id)), json.dumps(schedule)
        )
        return schedule

    async def list_schedules(self, device_id: uuid.UUID) -> list[dict[str, Any]]:
        """List schedules/timers configured for a device (Req 9.3)."""
        device = await self._get_device(device_id)
        raw = await self._redis.lrange(rk.command_schedule_key(str(device.id)), 0, -1)
        return [json.loads(item) for item in raw]


class CommandQueueError(AppError):
    """The offline command queue operation failed; the command is rejected (Req 9.5)."""

    error_code = "command_queue_failed"
    status_code = 503
