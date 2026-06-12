"""Device-domain models: devices, mqtt_credentials, device_groups,
device_sensors, device_user_assignments. See design.md Table Catalog.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base, TenantMixin, TimestampMixin, uuid_pk


class DeviceGroup(Base, TenantMixin, TimestampMixin):
    """A named grouping of devices (Req 5.5)."""

    __tablename__ = "device_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Device(Base, TenantMixin, TimestampMixin):
    """A physical or simulated IoT device."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = uuid_pk()
    # hardware/QR identity (Req 5.2)
    device_uid: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    # custom label (Req 5.3, 5.4)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("device_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    # assigned MQTT node (Req 24.4)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("mqtt_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    # online / offline
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="offline")
    # (Req 5.7)
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # (Req 13)
    is_simulator: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # 0 = no publish (Req 13.3)
    sim_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="60"
    )
    firmware_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("templates.id", ondelete="SET NULL"),
        nullable=True,
    )


class MqttCredential(Base, TenantMixin):
    """Per-device authentication token (single Device Token, like Blynk)."""

    __tablename__ = "mqtt_credentials"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Single device token — used as MQTT username; no separate password needed.
    # Format: dT_{base64url} (32 chars). Unique across all devices.
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Legacy fields kept for backward compat; new devices use token only.
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_plain: Mapped[str | None] = mapped_column(Text, nullable=True)
    # iotaps/{org_id}/#
    acl_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # (Req 5.9)
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


class DeviceSensor(Base, TenantMixin):
    """A datastream (sensor/actuator channel) exposed by a device.

    Acts as a registry of known telemetry keys, their type, and valid range.
    Auto-populated from incoming telemetry (first-seen keys are registered) and
    can be manually configured by the user (add display names, set types/ranges).
    The widget settings dialog uses this to offer a dropdown instead of free-text.
    """

    __tablename__ = "device_sensors"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # sensor key matching the telemetry JSON key (e.g. "led1", "temperature")
    key: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-friendly label (e.g. "Living Room LED")
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Datastream type: sensor (read-only), toggle (on/off), slider (value range)
    pin_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="sensor")
    # Unit (°C, %, V, etc.) - for display only
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Valid range for slider/gauge widgets
    min_value: Mapped[float | None] = mapped_column(nullable=True)
    max_value: Mapped[float | None] = mapped_column(nullable=True)


class DeviceUserAssignment(Base, TenantMixin):
    """M:N devices <-> users (Req 2.4, 5.6)."""

    __tablename__ = "device_user_assignments"
    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="device_user"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
