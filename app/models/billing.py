"""Billing & monetization models: subscriptions, payments, coupons,
partner_wallets, commissions, payouts. See design.md Table Catalog.

Invariants (Req 18.x):
- partner_wallets.balance NUMERIC NOT NULL DEFAULT 0 CHECK (balance >= 0)
- commissions.amount NUMERIC NOT NULL CHECK (amount >= 0)
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, uuid_pk


class Coupon(Base, TimestampMixin):
    """Discount coupon (Req 26). Not tenant-scoped: managed by Super_Admin."""

    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # percent / fixed
    discount_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redemptions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    valid_until: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class Subscription(Base, TenantMixin):
    """A plan subscription, optionally scoped to a single device (Req 15-17)."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    # per-device recharge (Req 17.4)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    # free / pro
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    # monthly / yearly
    billing_cycle: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # active / past_due / cancelled
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_period_start: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("coupons.id", ondelete="SET NULL"),
        nullable=True,
    )
    razorpay_subscription_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class Payment(Base, TenantMixin):
    """A payment against a subscription (Req 17)."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="INR")
    # created / captured / failed / refunded
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # refund window 14 days (Req 17.5, 17.7)
    refunded_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PartnerWallet(Base, TenantMixin):
    """Project_Center commission balance (Req 18). One per org; balance >= 0."""

    __tablename__ = "partner_wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        UniqueConstraint("org_id", name="org_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    balance: Mapped[float] = mapped_column(
        Numeric, nullable=False, server_default="0"
    )


class Commission(Base, TenantMixin, TimestampMixin):
    """A commission credit to a partner wallet (Req 18.1-18.3, 26.1)."""

    __tablename__ = "commissions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("partner_wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    period_month: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)


class Payout(Base, TenantMixin):
    """A partner withdrawal request (Req 18.4-18.6, 26.3)."""

    __tablename__ = "payouts"

    id: Mapped[uuid.UUID] = uuid_pk()
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("partner_wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    # bank / upi
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PENDING / APPROVED / REJECTED / PAID
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="PENDING"
    )
    requested_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    razorpayx_payout_id: Mapped[str | None] = mapped_column(Text, nullable=True)
