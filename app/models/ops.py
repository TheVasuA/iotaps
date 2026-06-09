"""Operational & platform-service models: activity_logs, notifications, webhooks,
support_chats, changelog, scheduled_reports, login_attempts, blocked_ips,
audit_log. See design.md Table Catalog.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, uuid_pk


class ActivityLog(Base, TenantMixin, TimestampMixin):
    """Activity log for provisioning/assignment/rename/command/config (Req 5.8)."""

    __tablename__ = "activity_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Notification(Base, TenantMixin, TimestampMixin):
    """A delivered/queued notification (Req 20)."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # telegram / email / push / in_app
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


class Webhook(Base, TenantMixin):
    """An outbound webhook configuration (Req 20.3-20.4)."""

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class SupportChat(Base, TenantMixin, TimestampMixin):
    """Support chat message between Device_User and Project_Center (Req 21)."""

    __tablename__ = "support_chats"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    device_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_center_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # sender role (device_user / project_center)
    sender_role: Mapped[str | None] = mapped_column(Text, nullable=True)


class Changelog(Base):
    """A platform changelog entry (Req 22, 27.4). Not tenant-scoped."""

    __tablename__ = "changelog"

    id: Mapped[uuid.UUID] = uuid_pk()
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ScheduledReport(Base, TenantMixin):
    """A one-off or scheduled report definition (Req 14)."""

    __tablename__ = "scheduled_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # csv / pdf
    format: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
