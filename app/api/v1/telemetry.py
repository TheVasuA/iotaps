"""Telemetry query API endpoints (Task 5.7, Req 6.6).

Implements the read side of the telemetry pipeline from design.md
("Telemetry & Reports"):

    GET /devices/{id}/telemetry        ?from&to&resolution=raw|5m|1h|1d -> [points]
    GET /devices/{id}/telemetry/latest -> {data, ts}

Both routes are tenant-scoped (Req 3.2/3.3 via ``TenantScope``) and gated by
``require_device_access`` so a Device_User can only read telemetry for devices
explicitly assigned to them (Req 2.4), while Project_Center and Super_Admin read
within their normal scope. The ``resolution`` query parameter selects the raw
hypertable or one of the 5m/1h/1d downsampled rollups produced by the
Downsampler (Req 6.6).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.security.deps import require_device_access, tenant_scope
from app.core.security.principal import Principal
from app.core.security.tenant import TenantScope
from app.services.telemetry_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RESOLUTION_RAW,
    TelemetryPoint,
    TelemetryService,
)

router = APIRouter(prefix="/devices", tags=["telemetry"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TelemetryPointOut(BaseModel):
    ts: datetime
    data: dict


class LatestTelemetryOut(BaseModel):
    ts: datetime
    data: dict


def _point_out(point: TelemetryPoint) -> TelemetryPointOut:
    return TelemetryPointOut(ts=point.ts, data=point.data)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/{device_id}/telemetry", response_model=list[TelemetryPointOut])
async def get_telemetry(
    device_id: uuid.UUID,
    resolution: str = Query(default=RESOLUTION_RAW),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> list[TelemetryPointOut]:
    """Return telemetry points for a device at the requested resolution (Req 6.6).

    ``resolution`` is one of ``raw|5m|1h|1d``; an unknown value yields a 422.
    ``from``/``to`` bound the inclusive time range; results are ordered oldest
    first and capped at ``limit`` points.
    """
    service = TelemetryService(scope)
    points = await service.query(
        device_id,
        resolution=resolution,
        start=from_,
        end=to,
        limit=limit,
    )
    return [_point_out(p) for p in points]


@router.get("/{device_id}/telemetry/latest", response_model=LatestTelemetryOut)
async def get_latest_telemetry(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_device_access()),
) -> LatestTelemetryOut:
    """Return the most recent raw telemetry sample for a device."""
    from app.core.errors import NotFoundError

    service = TelemetryService(scope)
    point = await service.latest(device_id)
    if point is None:
        raise NotFoundError(
            "No telemetry recorded for this device",
            error_code="telemetry_not_found",
        )
    return LatestTelemetryOut(ts=point.ts, data=point.data)
