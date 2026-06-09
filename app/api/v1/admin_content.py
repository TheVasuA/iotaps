"""Super_Admin coupons, commission, referral & content API (Task 20.4).

Implements the Super_Admin admin endpoints from design.md ("Admin") for
requirement groups 26 (coupons / commission / referral) and 27 (site / template
/ notification / content):

    POST   /admin/coupons                  create a coupon                 (Req 26)
    GET    /admin/coupons                  list coupons                    (Req 26)
    GET    /admin/coupons/{id}             fetch a coupon                  (Req 26)
    PATCH  /admin/coupons/{id}             update a coupon                 (Req 26)
    DELETE /admin/coupons/{id}             delete a coupon                 (Req 26)
    PATCH  /admin/partners/{id}/commission set/clear commission override   (Req 26.1, 26.2)
    GET    /admin/referrals                referral tracking + fraud flags (Req 26.4)
    POST   /admin/templates                create a template               (Req 27.2)
    PATCH  /admin/templates/{id}           edit a template                 (Req 27.2)
    DELETE /admin/templates/{id}           delete a template               (Req 27.2)
    GET    /admin/notification-settings    read notification settings      (Req 27.3)
    PATCH  /admin/notification-settings    update notification settings    (Req 27.3)
    GET    /admin/site-analytics           site analytics                  (Req 27.1)

Every route is Super_Admin-only (``require_role(ROLE_SUPER_ADMIN)``). Coupons
and templates are global (non-tenant) catalogs managed by the platform operator,
so these use a bare DB session rather than a tenant scope. Changelog management
(Req 27.4) and payout approval (Req 26.3) are served by the existing
``changelog`` and ``partner`` routers respectively and are not duplicated here.

The endpoints live in a dedicated ``admin_content`` module (separate from other
admin routers) and are registered on the v1 aggregate router.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.services import admin_content_service

router = APIRouter(prefix="/admin", tags=["admin", "content"])

# Reusable Super_Admin guard (Req 26, 27 are Super_Admin-only).
_require_admin = require_role(ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Coupons (Req 26)
# ---------------------------------------------------------------------------
class CouponOut(BaseModel):
    id: str
    code: str
    discount_type: str
    value: Decimal
    max_redemptions: int | None
    redemptions: int
    valid_until: str | None
    active: bool


class CreateCouponRequest(BaseModel):
    code: str
    discount_type: str = Field(description="percent or fixed")
    value: Decimal
    max_redemptions: int | None = None
    valid_until: datetime.datetime | None = None
    active: bool = True

    model_config = {"extra": "forbid"}


class UpdateCouponRequest(BaseModel):
    discount_type: str | None = None
    value: Decimal | None = None
    max_redemptions: int | None = None
    valid_until: datetime.datetime | None = None
    active: bool | None = None

    model_config = {"extra": "forbid"}


@router.post("/coupons", response_model=CouponOut, status_code=201)
async def create_coupon(
    payload: CreateCouponRequest,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> CouponOut:
    """Create a discount coupon (Req 26)."""
    coupon = await admin_content_service.create_coupon(
        session,
        code=payload.code,
        discount_type=payload.discount_type,
        value=payload.value,
        max_redemptions=payload.max_redemptions,
        valid_until=payload.valid_until,
        active=payload.active,
    )
    return CouponOut(**admin_content_service.serialize_coupon(coupon))


@router.get("/coupons", response_model=list[CouponOut])
async def list_coupons(
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[CouponOut]:
    """List all coupons, newest first (Req 26)."""
    coupons = await admin_content_service.list_coupons(session)
    return [CouponOut(**admin_content_service.serialize_coupon(c)) for c in coupons]


@router.get("/coupons/{coupon_id}", response_model=CouponOut)
async def get_coupon(
    coupon_id: uuid.UUID,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> CouponOut:
    """Fetch a single coupon (Req 26)."""
    coupon = await admin_content_service.get_coupon(session, coupon_id)
    return CouponOut(**admin_content_service.serialize_coupon(coupon))


@router.patch("/coupons/{coupon_id}", response_model=CouponOut)
async def update_coupon(
    coupon_id: uuid.UUID,
    payload: UpdateCouponRequest,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> CouponOut:
    """Update a coupon's mutable fields (Req 26)."""
    coupon = await admin_content_service.update_coupon(
        session,
        coupon_id,
        discount_type=payload.discount_type,
        value=payload.value,
        max_redemptions=payload.max_redemptions,
        valid_until=payload.valid_until,
        active=payload.active,
    )
    return CouponOut(**admin_content_service.serialize_coupon(coupon))


@router.delete("/coupons/{coupon_id}", status_code=204, response_class=Response)
async def delete_coupon(
    coupon_id: uuid.UUID,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a coupon (Req 26)."""
    await admin_content_service.delete_coupon(session, coupon_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Per-partner commission override (Req 26.1, 26.2)
# ---------------------------------------------------------------------------
class CommissionOverrideRequest(BaseModel):
    # A numeric rate (including 0) sets the override; null clears it back to the
    # platform default. ``rate`` is required in the body, but may be null.
    rate: Decimal | None = Field(
        default=None,
        description="Override rate in rupees (0 is a valid 'no commission' setting); null clears the override",
    )

    model_config = {"extra": "forbid"}


class CommissionOverrideOut(BaseModel):
    org_id: str
    commission_rate_override: Decimal | None


@router.patch("/partners/{org_id}/commission", response_model=CommissionOverrideOut)
async def set_commission_override(
    org_id: uuid.UUID,
    payload: CommissionOverrideRequest,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> CommissionOverrideOut:
    """Set or clear a partner's commission override, including zero (Req 26.1, 26.2)."""
    org = await admin_content_service.set_commission_override(
        session, org_id, rate=payload.rate
    )
    override: Optional[Any] = org.commission_rate_override
    return CommissionOverrideOut(
        org_id=str(org.id),
        commission_rate_override=Decimal(str(override)) if override is not None else None,
    )


# ---------------------------------------------------------------------------
# Referral tracking with fraud flags (Req 26.4)
# ---------------------------------------------------------------------------
class ReferralFraudFlags(BaseModel):
    self_referral: bool
    duplicate_gmail: bool
    high_volume_referrer: bool


class ReferralRecordOut(BaseModel):
    id: str
    referrer_user_id: str
    referred_user_id: str | None
    referred_gmail: str | None
    status: str
    created_at: str | None
    fraud_flags: ReferralFraudFlags
    fraud: bool


@router.get("/referrals", response_model=list[ReferralRecordOut])
async def list_referrals(
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ReferralRecordOut]:
    """List referral records with fraud flags (Req 26.4)."""
    records = await admin_content_service.list_referrals_with_fraud_flags(session)
    return [ReferralRecordOut(**r) for r in records]


# ---------------------------------------------------------------------------
# Template CRUD (Req 27.2)
# ---------------------------------------------------------------------------
class TemplateOut(BaseModel):
    id: str
    category: str
    name: str
    arduino_code: str | None
    wiring_diagram_url: str | None
    dashboard_def: dict | None
    rules_def: dict | None


class CreateTemplateRequest(BaseModel):
    category: str = Field(description="student or company")
    name: str
    arduino_code: str | None = None
    wiring_diagram_url: str | None = None
    dashboard_def: dict | None = None
    rules_def: dict | None = None

    model_config = {"extra": "forbid"}


class UpdateTemplateRequest(BaseModel):
    category: str | None = None
    name: str | None = None
    arduino_code: str | None = None
    wiring_diagram_url: str | None = None
    dashboard_def: dict | None = None
    rules_def: dict | None = None

    model_config = {"extra": "forbid"}


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    payload: CreateTemplateRequest,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> TemplateOut:
    """Create a student/company template (Req 27.2)."""
    template = await admin_content_service.create_template(
        session,
        category=payload.category,
        name=payload.name,
        arduino_code=payload.arduino_code,
        wiring_diagram_url=payload.wiring_diagram_url,
        dashboard_def=payload.dashboard_def,
        rules_def=payload.rules_def,
    )
    return TemplateOut(**admin_content_service.serialize_template(template))


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    payload: UpdateTemplateRequest,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> TemplateOut:
    """Edit a template; only supplied fields change (Req 27.2)."""
    # Distinguish "field omitted" from an explicit null so nullable fields can
    # be cleared. ``model_dump`` with ``exclude_unset`` reports only fields the
    # client actually sent.
    sent = payload.model_dump(exclude_unset=True)
    extra: dict[str, Any] = {}
    for nullable_field in (
        "arduino_code",
        "wiring_diagram_url",
        "dashboard_def",
        "rules_def",
    ):
        if nullable_field in sent:
            extra[nullable_field] = sent[nullable_field]
    template = await admin_content_service.update_template(
        session,
        template_id,
        category=payload.category,
        name=payload.name,
        **extra,
    )
    return TemplateOut(**admin_content_service.serialize_template(template))


@router.delete("/templates/{template_id}", status_code=204, response_class=Response)
async def delete_template(
    template_id: uuid.UUID,
    _: Principal = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a template (Req 27.2)."""
    await admin_content_service.delete_template(session, template_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Notification settings (Req 27.3)
# ---------------------------------------------------------------------------
class NotificationSettingsRequest(BaseModel):
    telegram: dict | None = None
    push: dict | None = None
    email: dict | None = None

    model_config = {"extra": "forbid"}


@router.get("/notification-settings")
async def get_notification_settings(
    _: Principal = Depends(_require_admin),
) -> dict[str, Any]:
    """Return Telegram/push/email notification settings (Req 27.3)."""
    return await admin_content_service.get_notification_settings()


@router.patch("/notification-settings")
async def update_notification_settings(
    payload: NotificationSettingsRequest,
    _: Principal = Depends(_require_admin),
) -> dict[str, Any]:
    """Apply Telegram/push/email notification settings platform-wide (Req 27.3)."""
    return await admin_content_service.update_notification_settings(
        telegram=payload.telegram,
        push=payload.push,
        email=payload.email,
    )


# ---------------------------------------------------------------------------
# Site analytics (Req 27.1)
# ---------------------------------------------------------------------------
@router.get("/site-analytics")
async def get_site_analytics(
    _: Principal = Depends(_require_admin),
) -> dict[str, Any]:
    """Return site analytics: page views, visitors, sessions (Req 27.1)."""
    return await admin_content_service.get_site_analytics()
