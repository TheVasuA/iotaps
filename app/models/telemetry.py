"""Telemetry time-series model (TimescaleDB hypertable).

The ``telemetry`` table is converted into a hypertable in the migration via
``create_hypertable('telemetry', 'ts', ...)``. The composite primary key
``(device_id, ts)`` provides the idempotent upsert key used by the Batch_Writer
(design.md "Telemetry Batch Writer", Req 6.2).

Continuous aggregates (telemetry_5m / telemetry_1h / telemetry_1d) and the
compression policy are created in raw SQL within the migration, since they are
TimescaleDB-specific objects with no ORM representation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Telemetry(Base):
    """Raw time-series telemetry. Hypertable partitioned on ``ts``."""

    __tablename__ = "telemetry"

    org_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, nullable=False
    )
    ts: Mapped[object] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    # {"temp": 24.1, "hum": 60}
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
