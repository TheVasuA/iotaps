"""Infrastructure / platform models: mqtt_nodes, templates, platform_settings.
See design.md Table Catalog.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class MqttNode(Base, TimestampMixin):
    """A registered Mosquitto node with capacity + resource metrics (Req 24, 32.2)."""

    __tablename__ = "mqtt_nodes"

    id: Mapped[uuid.UUID] = uuid_pk()
    ip: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    active_connections: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    # per-node resource metrics (Req 24.3)
    ram_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    cpu_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    disk_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class Template(Base):
    """A project template (student/company) with code + dashboard/rule defs (Req 11)."""

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    # student / company
    category: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    arduino_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    wiring_diagram_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    dashboard_def: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rules_def: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PlatformSetting(Base):
    """Key/value platform settings, read-through cached in Redis (Req 29.4)."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
