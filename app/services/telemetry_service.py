"""Telemetry query service (Task 5.7, Req 6.6).

Backs the read side of the telemetry pipeline exposed under the Devices API
(design.md "Telemetry & Reports"):

    GET /devices/{id}/telemetry        ?from&to&resolution=raw|5m|1h|1d -> [points]
    GET /devices/{id}/telemetry/latest -> {data, ts}

The ``resolution`` selects the source relation:

    raw -> the ``telemetry`` hypertable (per-message rows)
    5m  -> the ``telemetry_5m`` continuous aggregate (5-minute rollup)
    1h  -> the ``telemetry_1h`` continuous aggregate (1-hour rollup)
    1d  -> the ``telemetry_1d`` continuous aggregate (1-day rollup)

The rollup views are produced by the Downsampler (Req 6.6); the raw and rollup
relations share the ``(device_id, org_id, <time>, data)`` shape, differing only
in the time column name (``ts`` for raw, ``bucket`` for the aggregates).

The service is transport-agnostic: it takes a :class:`TenantScope` (carrying the
principal + session and enforcing tenant isolation) and returns plain dicts. The
device is first loaded through ``scope.get`` so a cross-org id is denied (Req 3.3)
and the query is then bound to that device's ``org_id`` so a Super_Admin reading
cross-org still gets correctly scoped rows.

Security note: the source relation name is chosen from a fixed internal
allowlist keyed by ``resolution`` and is *never* derived from raw user input, so
inlining it into the SQL text is safe; all filter values are bound parameters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, Integer, Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.core.security.tenant import TenantScope
from app.models.device import Device

# Valid resolution values accepted on the query string (design.md).
RESOLUTION_RAW = "raw"
RESOLUTION_5M = "5m"
RESOLUTION_1H = "1h"
RESOLUTION_1D = "1d"

VALID_RESOLUTIONS = (RESOLUTION_RAW, RESOLUTION_5M, RESOLUTION_1H, RESOLUTION_1D)

# Hard cap on points returned in a single response so an unbounded range cannot
# exhaust memory; clients page via ``from``/``to``.
DEFAULT_LIMIT = 1000
MAX_LIMIT = 10000


@dataclass(frozen=True)
class _Source:
    """A telemetry source relation and the name of its timestamp column."""

    relation: str
    time_column: str


# Allowlist mapping resolution -> (relation, time column). The relation names
# come from the schema migration (raw hypertable + continuous aggregates) and
# are fixed strings, never user input.
_SOURCES: dict[str, _Source] = {
    RESOLUTION_RAW: _Source("telemetry", "ts"),
    RESOLUTION_5M: _Source("telemetry_5m", "bucket"),
    RESOLUTION_1H: _Source("telemetry_1h", "bucket"),
    RESOLUTION_1D: _Source("telemetry_1d", "bucket"),
}


def resolve_source(resolution: str) -> _Source:
    """Return the source relation for ``resolution`` (validating it).

    Raises :class:`ValidationError` (422) for an unknown resolution so the
    relation name is always drawn from the allowlist.
    """
    source = _SOURCES.get(resolution)
    if source is None:
        raise ValidationError(
            f"Unknown resolution {resolution!r}; expected one of "
            f"{', '.join(VALID_RESOLUTIONS)}",
            error_code="invalid_resolution",
        )
    return source


@dataclass(frozen=True)
class TelemetryPoint:
    """A single telemetry sample (raw row or rollup bucket)."""

    ts: datetime
    data: dict


class TelemetryService:
    """Tenant-scoped read access to raw and downsampled telemetry."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session

    async def _device_org_id(self, device_id: uuid.UUID) -> uuid.UUID:
        """Load the device (enforcing tenant ownership) and return its org_id.

        Loading through ``scope.get`` denies a cross-org device id with a 403
        (Req 3.3); the returned org_id then scopes the telemetry query so even a
        Super_Admin reading cross-org gets only that device's organization.
        """
        device: Device = await self._scope.get(Device, device_id)
        return uuid.UUID(str(device.org_id))

    async def query(
        self,
        device_id: uuid.UUID,
        *,
        resolution: str = RESOLUTION_RAW,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[TelemetryPoint]:
        """Return telemetry points for a device, ordered oldest -> newest.

        ``resolution`` selects the raw hypertable or a downsampled rollup;
        ``start``/``end`` bound the (inclusive) time range; ``limit`` caps the
        number of points (clamped to ``MAX_LIMIT``).
        """
        source = resolve_source(resolution)
        org_id = await self._device_org_id(device_id)
        limit = max(1, min(int(limit), MAX_LIMIT))

        col = source.time_column
        stmt = text(
            f"SELECT {col} AS ts, data FROM {source.relation} "
            "WHERE device_id = :device_id AND org_id = :org_id "
            f"AND (:start IS NULL OR {col} >= :start) "
            f"AND (:end IS NULL OR {col} <= :end) "
            f"ORDER BY {col} ASC "
            "LIMIT :limit"
        ).bindparams(
            bindparam("device_id", type_=Uuid()),
            bindparam("org_id", type_=Uuid()),
            bindparam("start", type_=DateTime(timezone=True)),
            bindparam("end", type_=DateTime(timezone=True)),
            bindparam("limit", type_=Integer()),
        )
        result = await self._session.execute(
            stmt,
            {
                "device_id": device_id,
                "org_id": org_id,
                "start": start,
                "end": end,
                "limit": limit,
            },
        )
        return [TelemetryPoint(ts=row.ts, data=_as_dict(row.data)) for row in result]

    async def latest(self, device_id: uuid.UUID) -> TelemetryPoint | None:
        """Return the most recent raw telemetry sample, or ``None`` if none."""
        org_id = await self._device_org_id(device_id)
        stmt = text(
            "SELECT ts, data FROM telemetry "
            "WHERE device_id = :device_id AND org_id = :org_id "
            "ORDER BY ts DESC LIMIT 1"
        ).bindparams(
            bindparam("device_id", type_=Uuid()),
            bindparam("org_id", type_=Uuid()),
        )
        result = await self._session.execute(
            stmt, {"device_id": device_id, "org_id": org_id}
        )
        row = result.first()
        if row is None:
            return None
        return TelemetryPoint(ts=row.ts, data=_as_dict(row.data))


def _as_dict(data: object) -> dict:
    """Normalise a JSON/JSONB column value into a dict.

    asyncpg/JSONB returns a ``dict`` already; SQLite's JSON returns a ``str``
    that must be decoded. Anything else is wrapped defensively.
    """
    if isinstance(data, dict):
        return data
    if isinstance(data, (str, bytes)):
        import json

        try:
            decoded = json.loads(data)
        except (ValueError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}
