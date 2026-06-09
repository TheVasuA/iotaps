"""Security models: login_attempts, blocked_ips, audit_log (Req 29.2-29.3).

These are platform-wide operational/security tables and are not tenant-scoped.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class LoginAttempt(Base, TimestampMixin):
    """Records authentication attempts for brute-force detection (Req 29.2)."""

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    ip: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)


class BlockedIp(Base, TimestampMixin):
    """An IP blocked after exceeding the failure threshold (Req 29.3)."""

    __tablename__ = "blocked_ips"

    id: Mapped[uuid.UUID] = uuid_pk()
    ip: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_until: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditLog(Base, TimestampMixin):
    """Admin action audit trail (Req 29.2)."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
