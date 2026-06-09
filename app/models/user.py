"""User model. See design.md Table Catalog: users."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, uuid_pk


class User(Base, TenantMixin, TimestampMixin):
    """A platform user account (Super_Admin / Project_Center / Device_User)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # referral one-per-gmail (Req 19.6)
    gmail_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    # argon2/bcrypt salted; NULL for OAuth-only accounts
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # legacy/invalid format -> force reset (Req 1.9)
    password_format: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="argon2"
    )
    # super_admin / project_center / device_user
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # google
    oauth_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    twofa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    twofa_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    # light / dark (Req 4.4)
    theme_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="light"
    )
    referred_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # (Req 22.2) "What's new" popup tracking
    last_changelog_seen_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
