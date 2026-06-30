"""Razorpay subscription & payment flow (Task 15.1, Req 17.1-17.4, 17.6).

Implements the two halves of the design's payment flow
(design.md "Billing, Partner, Referral"):

    POST /billing/subscribe   -> create a Razorpay order for a per-device or
                                 fleet Pro_Plan purchase, with optional coupon.
    POST /billing/webhook     -> on a signature-verified ``payment.captured``
                                 event, activate/extend the subscription; on
                                 ``payment.failed`` retain the prior state and
                                 notify the customer.

Design decisions:

- **One source of pricing truth.** Unit price/total come from
  :mod:`app.services.billing_service` so the order amount always matches the
  published quote (Req 16). A coupon, when supplied, is applied on top of that
  total (percent or fixed-rupee discount, never below ₹0).
- **Per-device vs fleet.** ``device_id`` is optional. When present the
  subscription is scoped to that one device (Req 17.4); otherwise it is a fleet
  purchase covering ``device_count`` devices.
- **Pending → active.** ``subscribe`` creates the ``Subscription`` (status
  ``created``) and a ``Payment`` (status ``created``) carrying the Razorpay
  ``order_id``. The webhook is what flips them to active/captured once Razorpay
  confirms the money moved (Req 17.2) - so a created-but-unpaid order never
  grants Pro access.
- **Failure safety.** A ``payment.failed`` webhook marks the payment failed but
  leaves the subscription's prior ``status``/period untouched and records a
  notification for the org (Req 17.3).
- **Auto-debit renewal.** A renewal capture (recurring auto-debit, Req 17.6)
  extends the period from the later of "now" and the current period end, so
  consecutive renewals stack instead of overlapping.

The webhook handler is tenant-agnostic (Razorpay calls it unauthenticated, with
a signed body); it resolves the org from the stored payment/subscription rather
than from a JWT. Signature verification lives in
:mod:`app.services.razorpay_client`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security.tenant import TenantScope
from app.models.billing import Coupon, Payment, Subscription
from app.models.device import Device
from app.models.ops import Notification
from app.models.user import User
from app.services import billing_service
from app.services.razorpay_client import (
    PAISE_PER_RUPEE,
    RazorpayClient,
    RazorpayOrder,
    RazorpayRefund,
)

logger = get_logger(__name__)

# Plan purchased through the paid subscription flow (Free needs no payment).
PRO_PLAN = "pro"

# Subscription / payment status values (mirror design.md Table Catalog).
SUB_STATUS_CREATED = "created"
SUB_STATUS_ACTIVE = "active"
SUB_STATUS_PAST_DUE = "past_due"

PAY_STATUS_CREATED = "created"
PAY_STATUS_CAPTURED = "captured"
PAY_STATUS_FAILED = "failed"
PAY_STATUS_REFUNDED = "refunded"

# Money-back guarantee window: a refund is accepted only within 14 days of the
# purchase (Req 17.5); a request after the window is rejected (Req 17.7).
REFUND_WINDOW_DAYS = 14

# Razorpay webhook event names we act on (Req 17.2, 17.3).
EVENT_PAYMENT_CAPTURED = "payment.captured"
EVENT_PAYMENT_FAILED = "payment.failed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_period(start: datetime, billing_cycle: str) -> datetime:
    """Return ``start`` advanced by one billing period (calendar-correct).

    Monthly advances by one calendar month (clamping day-of-month for short
    months); yearly advances by one year. Keeps renewals aligned to the
    calendar rather than a fixed 30/365-day approximation.
    """
    cycle = billing_service.normalize_cycle(billing_cycle)
    if cycle == billing_service.CYCLE_YEARLY:
        try:
            return start.replace(year=start.year + 1)
        except ValueError:  # Feb 29 -> Feb 28 on a non-leap target year
            return start.replace(year=start.year + 1, day=28)
    # Monthly: roll the month, carrying into the next year in December.
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    day = start.day
    while True:
        try:
            return start.replace(year=year, month=month, day=day)
        except ValueError:
            # Day overflow (e.g. Jan 31 -> Feb): step back to a valid day.
            day -= 1
            if day < 28:  # safety floor; every month has >= 28 days
                return start.replace(year=year, month=month, day=28)


def apply_coupon_discount(total: int, coupon: Optional[Coupon]) -> int:
    """Apply a coupon to a rupee ``total``, never returning below ₹0.

    ``percent`` coupons take ``value`` percent off; ``fixed`` coupons subtract a
    flat ``value`` rupees. An inactive coupon, or one past ``valid_until`` / its
    redemption cap, leaves the total unchanged (validation happens in the
    caller, which raises for an unusable coupon; this helper is pure math).
    """
    if coupon is None:
        return total
    value = float(coupon.value or 0)
    if coupon.discount_type == "percent":
        discounted = total - (total * value / 100.0)
    elif coupon.discount_type == "fixed":
        discounted = total - value
    else:
        return total
    return max(0, int(round(discounted)))


class SubscriptionService:
    """Tenant-scoped subscribe flow + tenant-agnostic webhook processing."""

    def __init__(self, scope: TenantScope, razorpay: RazorpayClient) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session
        self._razorpay = razorpay

    @property
    def _org_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.org_id))

    # ------------------------------------------------------------------
    # Subscribe: create a Razorpay order (Req 17.1, 17.4)
    # ------------------------------------------------------------------
    async def _resolve_coupon(self, code: Optional[str]) -> Optional[Coupon]:
        """Look up and validate a coupon code; raise if unusable (Req 26)."""
        if not code:
            return None
        result = await self._session.execute(
            select(Coupon).where(Coupon.code == code)
        )
        coupon = result.scalar_one_or_none()
        if coupon is None:
            raise NotFoundError("Coupon not found", error_code="coupon_not_found")
        if not coupon.active:
            raise ValidationError("Coupon is not active", error_code="coupon_inactive")
        if coupon.valid_until is not None:
            valid_until = coupon.valid_until
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if valid_until < _now():
                raise ValidationError(
                    "Coupon has expired", error_code="coupon_expired"
                )
        if (
            coupon.max_redemptions is not None
            and (coupon.redemptions or 0) >= coupon.max_redemptions
        ):
            raise ValidationError(
                "Coupon redemption limit reached", error_code="coupon_exhausted"
            )
        return coupon

    async def subscribe(
        self,
        *,
        device_count: int,
        billing_cycle: str,
        device_id: Optional[uuid.UUID] = None,
        coupon_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a Pro_Plan subscription order (Req 17.1, 17.4).

        Resolves the volume-tier price, applies any coupon, persists a
        ``Subscription`` (status ``created``) and a ``Payment`` (status
        ``created``) bound to a freshly created Razorpay order, and returns the
        order for the client to complete checkout. Activation happens later via
        the webhook (Req 17.2), so this does not grant Pro access yet.
        """
        cycle = billing_service.normalize_cycle(billing_cycle)
        per_device = billing_service.unit_price(device_count, cycle)
        gross_total = device_count * per_device

        # Per-device purchase must reference a device in the caller's org.
        if device_id is not None:
            await self._scope.get(Device, device_id)

        coupon = await self._resolve_coupon(coupon_code)
        net_total = apply_coupon_discount(gross_total, coupon)

        subscription = Subscription(
            org_id=self._org_uuid,
            device_id=device_id,
            plan=PRO_PLAN,
            billing_cycle=cycle,
            device_count=device_count,
            unit_price=per_device,
            status=SUB_STATUS_CREATED,
            coupon_id=coupon.id if coupon is not None else None,
        )
        self._session.add(subscription)
        await self._session.flush()  # assign subscription.id

        order: RazorpayOrder = self._razorpay.create_order(
            amount=net_total * PAISE_PER_RUPEE,
            currency="INR",
            receipt=f"sub_{subscription.id}",
        )

        payment = Payment(
            org_id=self._org_uuid,
            subscription_id=subscription.id,
            amount=net_total,
            currency=order.currency,
            status=PAY_STATUS_CREATED,
            razorpay_order_id=order.id,
        )
        self._session.add(payment)
        subscription.razorpay_subscription_id = order.id
        await self._session.commit()
        await self._session.refresh(subscription)
        await self._session.refresh(payment)

        return {
            "subscription_id": str(subscription.id),
            "razorpay_order": {
                "id": order.id,
                "amount": order.amount,
                "currency": order.currency,
                "receipt": order.receipt,
                "status": order.status,
            },
            "device_count": device_count,
            "billing_cycle": cycle,
            "unit_price": per_device,
            "gross_total": gross_total,
            "amount_due": net_total,
            "coupon_applied": coupon.code if coupon is not None else None,
        }

    # ------------------------------------------------------------------
    # Refund: enforce the 14-day money-back window (Req 17.5, 17.7)
    # ------------------------------------------------------------------
    async def refund(self, *, payment_id: uuid.UUID) -> dict[str, Any]:
        """Refund a captured payment if within the 14-day window (Req 17.5, 17.7).

        Resolves the tenant-scoped payment, verifies it is a captured payment
        eligible for refund, and checks the request falls within
        :data:`REFUND_WINDOW_DAYS` days of purchase. A request inside the window
        is processed through Razorpay (the Payment_Gateway) and the payment is
        marked ``refunded``; a request after the window is rejected (Req 17.7).
        """
        payment: Payment = await self._scope.get(Payment, payment_id)

        if payment.status == PAY_STATUS_REFUNDED:
            raise ValidationError(
                "Payment has already been refunded",
                error_code="already_refunded",
            )
        if payment.status != PAY_STATUS_CAPTURED:
            raise ValidationError(
                "Only a captured payment can be refunded",
                error_code="payment_not_refundable",
            )
        if payment.paid_at is None:
            raise ValidationError(
                "Payment has no purchase timestamp to refund against",
                error_code="payment_not_refundable",
            )

        requested_at = _now()
        if not within_refund_window(payment.paid_at, requested_at):
            # Past the money-back guarantee window (Req 17.7).
            raise ValidationError(
                "Refund window has elapsed; the request cannot be processed",
                error_code="refund_window_elapsed",
            )

        if not payment.razorpay_payment_id:
            raise ValidationError(
                "Payment is missing a Razorpay payment id to refund",
                error_code="payment_not_refundable",
            )

        amount_rupees = int(payment.amount)
        refund: RazorpayRefund = self._razorpay.create_refund(
            payment_id=payment.razorpay_payment_id,
            amount=amount_rupees * PAISE_PER_RUPEE,
            currency=payment.currency or "INR",
        )

        payment.status = PAY_STATUS_REFUNDED
        payment.refunded_at = requested_at
        await self._session.commit()
        await self._session.refresh(payment)

        return {
            "payment_id": str(payment.id),
            "status": payment.status,
            "refunded_at": payment.refunded_at,
            "razorpay_refund": {
                "id": refund.id,
                "payment_id": refund.payment_id,
                "amount": refund.amount,
                "currency": refund.currency,
                "status": refund.status,
            },
        }


def within_refund_window(paid_at: datetime, requested_at: datetime) -> bool:
    """Whether a refund requested at ``requested_at`` is inside the 14-day window.

    A refund is accepted if and only if it is requested within
    :data:`REFUND_WINDOW_DAYS` days of the purchase (``paid_at``) - the
    money-back guarantee boundary (Req 17.5, 17.7). Naive datetimes are treated
    as UTC so the comparison is correct regardless of how the timestamp was
    persisted (Postgres timestamptz vs SQLite-backed tests).
    """
    if paid_at.tzinfo is None:
        paid_at = paid_at.replace(tzinfo=timezone.utc)
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    # Inclusive boundary: a request exactly 14 days after purchase is allowed.
    return requested_at <= paid_at + timedelta(days=REFUND_WINDOW_DAYS)


# ---------------------------------------------------------------------------
# Webhook processing (tenant-agnostic; Req 17.2, 17.3, 17.6)
# ---------------------------------------------------------------------------
def _extract_payment_entity(event: dict[str, Any]) -> dict[str, Any]:
    """Pull the ``payment`` entity from a Razorpay webhook payload.

    Razorpay nests it under ``payload.payment.entity``; fall back gracefully so
    a slightly different shape still yields whatever fields are present.
    """
    payload = event.get("payload", {}) or {}
    payment = payload.get("payment", {}) or {}
    entity = payment.get("entity", {}) or {}
    return entity


async def _find_payment(
    session: AsyncSession, order_id: Optional[str], payment_id: Optional[str]
) -> Optional[Payment]:
    """Locate the platform Payment row for a webhook event.

    Matches on the Razorpay order id first (set at subscribe time), then on the
    Razorpay payment id (set on a prior capture) so repeat events for the same
    payment are idempotent.
    """
    if order_id:
        result = await session.execute(
            select(Payment).where(Payment.razorpay_order_id == order_id)
        )
        payment = result.scalars().first()
        if payment is not None:
            return payment
    if payment_id:
        result = await session.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        )
        return result.scalars().first()
    return None


async def _notify_org(
    session: AsyncSession, org_id: uuid.UUID, *, title: str, body: str
) -> None:
    """Record an in-app notification for the org's users (Req 17.3, 20).

    Notifies every user in the organization so the customer sees the payment
    failure regardless of which account initiated checkout. Best-effort: if the
    org has no users, nothing is recorded.
    """
    result = await session.execute(select(User.id).where(User.org_id == org_id))
    user_ids = [row[0] for row in result.all()]
    for user_id in user_ids:
        session.add(
            Notification(
                org_id=org_id,
                user_id=user_id,
                channel="in_app",
                title=title,
                body=body,
            )
        )


async def process_webhook_event(session: AsyncSession, event: dict[str, Any]) -> str:
    """Apply a verified Razorpay webhook event to billing state.

    Returns a short status string describing the outcome (``captured``,
    ``failed``, ``ignored``, ``unmatched``). Signature verification is the
    caller's responsibility (the router rejects bad signatures before this is
    reached, Req 17.2).
    """
    event_type = event.get("event")
    entity = _extract_payment_entity(event)
    order_id = entity.get("order_id")
    razorpay_payment_id = entity.get("id")

    if event_type not in (EVENT_PAYMENT_CAPTURED, EVENT_PAYMENT_FAILED):
        return "ignored"

    payment = await _find_payment(session, order_id, razorpay_payment_id)
    if payment is None:
        logger.warning(
            "razorpay_webhook_unmatched",
            extra={"event": event_type, "order_id": order_id},
        )
        return "unmatched"

    subscription = (
        await session.get(Subscription, payment.subscription_id)
        if payment.subscription_id is not None
        else None
    )

    if event_type == EVENT_PAYMENT_CAPTURED:
        await _handle_capture(session, payment, subscription, razorpay_payment_id)
        await session.commit()
        return "captured"

    # payment.failed -> retain prior subscription state + notify (Req 17.3).
    await _handle_failure(session, payment, subscription)
    await session.commit()
    return "failed"


async def _handle_capture(
    session: AsyncSession,
    payment: Payment,
    subscription: Optional[Subscription],
    razorpay_payment_id: Optional[str],
) -> None:
    """Activate/extend the subscription on a successful capture (Req 17.2, 17.6).

    Idempotent: a duplicate capture for an already-captured payment does not
    re-extend the period.
    """
    if payment.status == PAY_STATUS_CAPTURED:
        return  # already processed; ignore the duplicate event

    payment.status = PAY_STATUS_CAPTURED
    payment.paid_at = _now()
    if razorpay_payment_id:
        payment.razorpay_payment_id = razorpay_payment_id

    if subscription is None:
        return

    now = _now()
    # Extend from the later of now / current period end so an early renewal
    # (auto-debit, Req 17.6) stacks onto the remaining time instead of
    # truncating it.
    current_end = subscription.current_period_end
    if current_end is not None and current_end.tzinfo is None:
        current_end = current_end.replace(tzinfo=timezone.utc)
    base = current_end if current_end is not None and current_end > now else now

    if subscription.current_period_start is None:
        subscription.current_period_start = now
    subscription.current_period_end = _add_period(
        base, subscription.billing_cycle or billing_service.CYCLE_MONTHLY
    )
    subscription.status = SUB_STATUS_ACTIVE

    # Best-effort confirmation email (never breaks webhook processing).
    try:
        from app.services import email_service

        await email_service.notify_payment_succeeded(
            session,
            payment.org_id,
            amount=payment.amount,
            currency=payment.currency or "INR",
            period_end=subscription.current_period_end,
        )
    except Exception:  # noqa: BLE001
        logger.warning("payment_success_email_failed", exc_info=True)


async def _handle_failure(
    session: AsyncSession,
    payment: Payment,
    subscription: Optional[Subscription],
) -> None:
    """Mark the payment failed, retain prior subscription state, notify (Req 17.3)."""
    # An already-captured payment is not downgraded by a stray failure event.
    if payment.status == PAY_STATUS_CAPTURED:
        return
    payment.status = PAY_STATUS_FAILED
    # Deliberately do NOT touch subscription.status / period: the prior state is
    # retained (Req 17.3).
    await _notify_org(
        session,
        payment.org_id,
        title="Payment failed",
        body=(
            "Your subscription payment could not be processed. "
            "Your previous plan remains unchanged. Please try again."
        ),
    )

    # Best-effort failure email in addition to the in-app notification.
    try:
        from app.services import email_service

        await email_service.notify_payment_failed(
            session, payment.org_id, amount=payment.amount, currency=payment.currency or "INR"
        )
    except Exception:  # noqa: BLE001
        logger.warning("payment_failed_email_failed", exc_info=True)
