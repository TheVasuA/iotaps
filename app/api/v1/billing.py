"""Billing API endpoints (Tasks 14.3 & 15.1, Req 16, 17).

Implements the billing surface from design.md ("Billing, Partner, Referral"):

    GET    /billing/plans                  -> {free, pro, pricing_tiers}
    POST   /billing/quote   {device_count, billing_cycle} -> {unit_price, total}
    POST   /billing/subscribe              -> {razorpay_order}   (per-device/fleet, coupon)
    POST   /billing/webhook  (Razorpay signed) -> {status}

Plans/quote are pure pricing reads backed by
:mod:`app.services.billing_service` - no tenant data is touched, so they only
require an authenticated principal. ``/subscribe`` creates a Razorpay order and
persists a pending subscription + payment (tenant-scoped, Project_Center). The
``/webhook`` is called unauthenticated by Razorpay with a signed body; it
verifies the signature before activating/extending (capture) or retaining state
+ notifying (failure). All Razorpay interaction is abstracted in
:mod:`app.services.razorpay_client` so no live API call/secret is needed.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ValidationError
from app.core.security.deps import get_principal, require_role, tenant_scope
from app.core.security.principal import (
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.db.session import get_session
from app.services import billing_service
from app.services.razorpay_client import get_razorpay_client, verify_webhook_signature
from app.services.subscription_service import SubscriptionService, process_webhook_event

router = APIRouter(prefix="/billing", tags=["billing"])

# Roles permitted to purchase a subscription (Super_Admin is always allowed by
# require_role; listing Project_Center documents intent).
_SUBSCRIBE_ROLES = (ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PricingTierOut(BaseModel):
    min_devices: int
    max_devices: int | None
    unit_price_monthly: int


class PlansResponse(BaseModel):
    free: dict
    pro: dict
    pricing_tiers: list[PricingTierOut]


class QuoteRequest(BaseModel):
    device_count: int = Field(ge=1, description="Number of devices being purchased")
    billing_cycle: str = Field(description="'monthly' or 'yearly'")


class QuoteResponse(BaseModel):
    device_count: int
    billing_cycle: str
    unit_price: int
    total: int


class SubscribeRequest(BaseModel):
    # Optional: scope the subscription to a single device (per-device recharge,
    # Req 17.4). Omit for a fleet purchase covering ``device_count`` devices.
    device_id: uuid.UUID | None = None
    device_count: int = Field(ge=1, description="Number of devices to subscribe")
    billing_cycle: str = Field(description="'monthly' or 'yearly'")
    coupon: str | None = Field(default=None, description="Optional coupon code")

    model_config = {"extra": "forbid"}


class RazorpayOrderOut(BaseModel):
    id: str
    amount: int
    currency: str
    receipt: str | None
    status: str


class SubscribeResponse(BaseModel):
    subscription_id: str
    razorpay_order: RazorpayOrderOut
    device_count: int
    billing_cycle: str
    unit_price: int
    gross_total: int
    amount_due: int
    coupon_applied: str | None


class WebhookResponse(BaseModel):
    status: str


class RefundRequest(BaseModel):
    payment_id: uuid.UUID = Field(description="Payment to refund")

    model_config = {"extra": "forbid"}


class RazorpayRefundOut(BaseModel):
    id: str
    payment_id: str
    amount: int
    currency: str
    status: str


class RefundResponse(BaseModel):
    payment_id: str
    status: str
    refunded_at: datetime | None
    razorpay_refund: RazorpayRefundOut


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/plans", response_model=PlansResponse)
async def get_plans(
    _: Principal = Depends(get_principal),
) -> PlansResponse:
    """Return the Free/Pro plans and the volume-discount tiers (Req 16.1-16.5)."""
    return PlansResponse(**billing_service.plans())


@router.post("/quote", response_model=QuoteResponse)
async def post_quote(
    payload: QuoteRequest,
    _: Principal = Depends(get_principal),
) -> QuoteResponse:
    """Quote a purchase: resolve the volume-tier unit price and total (Req 16.2-16.7)."""
    return QuoteResponse(**billing_service.quote(payload.device_count, payload.billing_cycle))


@router.post("/subscribe", response_model=SubscribeResponse, status_code=201)
async def post_subscribe(
    payload: SubscribeRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_SUBSCRIBE_ROLES)),
) -> SubscribeResponse:
    """Create a Razorpay order for a per-device or fleet Pro_Plan purchase (Req 17.1, 17.4).

    Resolves the volume-tier price, applies an optional coupon, and persists a
    pending subscription + payment bound to the order. Activation happens when
    Razorpay confirms capture via the webhook (Req 17.2).
    """
    service = SubscriptionService(scope, get_razorpay_client())
    result = await service.subscribe(
        device_count=payload.device_count,
        billing_cycle=payload.billing_cycle,
        device_id=payload.device_id,
        coupon_code=payload.coupon,
    )
    return SubscribeResponse(**result)


@router.post("/refund", response_model=RefundResponse)
async def post_refund(
    payload: RefundRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_SUBSCRIBE_ROLES)),
) -> RefundResponse:
    """Refund a captured payment under the 14-day money-back guarantee (Req 17.5, 17.7).

    Accepts and processes the refund through Razorpay when the request falls
    within 14 days of purchase (``paid_at``); rejects it once the window has
    elapsed. The payment must belong to the caller's organization.
    """
    service = SubscriptionService(scope, get_razorpay_client())
    result = await service.refund(payment_id=payload.payment_id)
    return RefundResponse(**result)


@router.post("/webhook", response_model=WebhookResponse)
async def post_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    session=Depends(get_session),
) -> WebhookResponse:
    """Process a signed Razorpay webhook (Req 17.2, 17.3, 17.6).

    Verifies the ``X-Razorpay-Signature`` over the raw body against the
    configured webhook secret before applying any state change; a missing or
    invalid signature is rejected with 401 so an unsigned/forged event can never
    activate a subscription. On ``payment.captured`` the subscription is
    activated/extended; on ``payment.failed`` the prior state is retained and
    the customer is notified.
    """
    raw_body = await request.body()
    secret = get_settings().razorpay_webhook_secret
    if not verify_webhook_signature(raw_body, x_razorpay_signature, secret):
        raise AuthenticationError(
            "Invalid Razorpay webhook signature", error_code="invalid_signature"
        )

    try:
        event = json.loads(raw_body)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Webhook body is not valid JSON") from exc
    if not isinstance(event, dict):
        raise ValidationError("Webhook body must be a JSON object")

    status = await process_webhook_event(session, event)
    return WebhookResponse(status=status)
