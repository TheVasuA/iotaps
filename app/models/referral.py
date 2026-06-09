"""Referral-program models: referrals, referral_rewards. See design.md Table Catalog."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class Referral(Base, TimestampMixin):
    """A recorded referral. Unique(referred_gmail) enforces one-per-gmail (Req 19.6)."""

    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referred_gmail", name="referred_gmail"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    referred_gmail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending / confirmed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")


class ReferralReward(Base):
    """A granted referral reward, capped at 3 devices/3 months (Req 19.5)."""

    __tablename__ = "referral_rewards"

    id: Mapped[uuid.UUID] = uuid_pk()
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    devices_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    months_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    granted_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
