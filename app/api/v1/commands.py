"""Device command API endpoints (Task 9.1, Req 9.1-9.7).

Implements the device-control surface from design.md ("Commands"):

    POST /devices/{id}/commands        {type: on|off|value, value?} -> {command_id, status}
    GET  /devices/{id}/commands/{cid}  -> {status: SENT|QUEUED|CONFIRMED|UNACKNOWLEDGED}
    POST /devices/{id}/schedules       {cron, type, value?} -> {schedule}
    GET  /devices/{id}/schedules       -> [schedule]

All routes are tenant-scoped (Req 3.2/3.3 via ``TenantScope``) and gated by
``require_device_access`` so a Device_User may only control devices assigned to
them (Req 2.4), while Project_Center and Super_Admin act within their normal
scope. Commands publish to the device's MQTT command topic when the device is
online (status SENT + ACK timer) and are queued in Redis when offline (status
QUEUED); a queue failure rejects the command (Req 9.5). ACK handling, ACK
timeout, and reconnect flush live in ``app.services.command_service``.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.redis_client import get_redis
from app.core.security.deps import require_device_access, tenant_scope
from app.core.security.principal import Principal
from app.core.security.tenant import TenantScope
from app.services.command_service import CommandRecord, CommandService

router = APIRouter(prefix="/devices", tags=["commands"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class IssueCommandRequest(BaseModel):
    type: str = Field(description="on | off | value")
    value: float | None = Field(default=None)

    model_config = {"extra": "forbid"}


class CommandStatusOut(BaseModel):
    command_id: str
    device_id: str
    type: str
    value: float | None
    status: str
    created_at: str
    updated_at: str


class CreateScheduleRequest(BaseModel):
    cron: str = Field(min_length=1)
    type: str = Field(description="on | off | value")
    value: float | None = Field(default=None)

    model_config = {"extra": "forbid"}


class ScheduleOut(BaseModel):
    schedule_id: str
    device_id: str
    cron: str
    command: dict


def _status_out(record: CommandRecord) -> CommandStatusOut:
    return CommandStatusOut(
        command_id=record.command_id,
        device_id=record.device_id,
        type=record.type,
        value=record.value,
        status=record.status.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---------------------------------------------------------------------------
# MQTT publisher — persistent connection pool for low-latency publishing.
# A per-request TCP+MQTT connection costs ~1-3s; a shared persistent client
# reduces command latency to <50ms (broker is on the same Docker network).
# ---------------------------------------------------------------------------
import asyncio
import logging

_mqtt_logger = logging.getLogger(__name__)

class _MqttPool:
    """Maintains a single persistent MQTT connection for publishing commands.

    Falls back to a one-shot connection if the persistent one is unavailable.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        self._client = None
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, payload: str) -> None:
        import aiomqtt

        settings = get_settings()

        # Try persistent connection first
        async with self._lock:
            if self._client is None:
                try:
                    self._client = aiomqtt.Client(
                        hostname=settings.mqtt_host,
                        port=settings.mqtt_port,
                        keepalive=60,
                    )
                    await self._client.__aenter__()
                except Exception:
                    self._client = None

            if self._client is not None:
                try:
                    await self._client.publish(topic, payload)
                    return
                except Exception:
                    # Connection died, clean up and fall through
                    try:
                        await self._client.__aexit__(None, None, None)
                    except Exception:
                        pass
                    self._client = None

        # Fallback: one-shot connection (slow but reliable)
        _mqtt_logger.warning("mqtt_pool_fallback", extra={"topic": topic})
        async with aiomqtt.Client(hostname=settings.mqtt_host, port=settings.mqtt_port) as client:
            await client.publish(topic, payload)

    async def close(self):
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.__aexit__(None, None, None)
                except Exception:
                    pass
                self._client = None


_mqtt_pool = _MqttPool()


async def _publish_command(topic: str, payload: str) -> None:
    """Publish a command payload to the MQTT broker via the persistent pool."""
    await _mqtt_pool.publish(topic, payload)


def _build_service(scope: TenantScope) -> CommandService:
    redis = get_redis()
    if redis is None:  # pragma: no cover - redis should be present in real envs
        raise AppError(
            "Command service unavailable: cache store is offline",
            error_code="service_unavailable",
            status_code=503,
        )
    return CommandService(scope, redis, _publish_command)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/{device_id}/commands", response_model=CommandStatusOut, status_code=201)
async def issue_command(
    device_id: uuid.UUID,
    payload: IssueCommandRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> CommandStatusOut:
    """Issue a command to a device (Req 9.1, 9.2, 9.5)."""
    service = _build_service(scope)
    settings = get_settings()
    record = await service.issue_command(
        device_id,
        type=payload.type,
        value=payload.value,
        ack_timeout_seconds=settings.command_ack_timeout_seconds,
    )
    return _status_out(record)


@router.get(
    "/{device_id}/commands/{command_id}", response_model=CommandStatusOut
)
async def get_command_status(
    device_id: uuid.UUID,
    command_id: str,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> CommandStatusOut:
    """Return a command's current status (Req 9.4-9.7)."""
    service = _build_service(scope)
    record = await service.get_command(device_id, command_id)
    return _status_out(record)


@router.post("/{device_id}/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    device_id: uuid.UUID,
    payload: CreateScheduleRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> ScheduleOut:
    """Create a schedule/timer for a device command (Req 9.3)."""
    service = _build_service(scope)
    schedule = await service.create_schedule(
        device_id, cron=payload.cron, type=payload.type, value=payload.value
    )
    return ScheduleOut(**{k: schedule[k] for k in ("schedule_id", "device_id", "cron", "command")})


@router.get("/{device_id}/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> list[ScheduleOut]:
    """List schedules/timers configured for a device (Req 9.3)."""
    service = _build_service(scope)
    schedules = await service.list_schedules(device_id)
    return [
        ScheduleOut(**{k: s[k] for k in ("schedule_id", "device_id", "cron", "command")})
        for s in schedules
    ]
