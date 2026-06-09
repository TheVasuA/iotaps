"""Super_Admin coupons, commission, referral, and content controls (Task 20.4).

Backs the Super_Admin admin surface from design.md ("Admin") for requirement
groups 26 (coupons / commission / referral) and 27 (site / template /
notification / content):

- **Coupon CRUD (Req 26.1 surface).** Create/list/update/delete discount
  coupons (``coupons`` table is global, not tenant-scoped - managed by the
  Super_Admin only).
- **Per-partner commission override (Req 26.2, 26.1).** Set an organization's
  ``commission_rate_override`` - *including a configured value of zero*, a valid
  "no commission" setting that must be honoured rather than treated as unset.
  Passing ``None`` clears the override so the partner falls back to the ₹50
  default (see :mod:`app.services.commission_service`).
- **Referral tracking with fraud flags (Req 26.4).** List referral records with
  per-record fraud flags derived from simple abuse heuristics (self-referral,
  duplicate Gmail identity, and an unusually high referral volume from one
  referrer).
- **Template CRUD (Req 27.2).** Create/edit/delete student or company templates
  in the global catalog.
- **Notification settings (Req 27.3).** Read/write the platform Telegram, push,
  and email notification settings via the platform-settings loader so they apply
  platform-wide immediately (Req 29.4 mechanism).
- **Site analytics (Req 27.1).** Surface page views, visitors, and sessions.

Changelog management (Req 27.4) reuses :mod:`app.services.changelog_service`;
payout approval (Req 26.3) already lives in :mod:`app.services.payout_service`.
Those are wired by the API layer rather than duplicated here.

Callers own the surrounding transaction unless a function documents its own
commit.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.settings_loader import get_setting, set_setting
from app.models.billing import Coupon
from app.models.infra import Template
from app.models.organization import Organization
from app.models.referral import Referral
from app.services.template_service import TEMPLATE_CATEGORIES

logger = get_logger(__name__)

# Sentinel distinguishing "field not supplied" from an explicit ``None`` so a
# nullable template field can be cleared via an update.
_UNSET: Any = object()

# Recognised coupon discount types (design.md coupons.discount_type, Req 26).
COUPON_DISCOUNT_TYPES = frozenset({"percent", "fixed"})

# Platform-settings key holding Telegram/push/email notification settings
# (Req 27.3). Stored via the read-through settings loader so a change applies
# platform-wide immediately (Req 29.4 mechanism).
NOTIFICATION_SETTINGS_KEY = "notification_settings"
_DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    "telegram": {"enabled": False, "bot_token": None},
    "push": {"enabled": False, "firebase_server_key": None},
    "email": {"enabled": False, "from_address": None},
}

# Platform-settings key holding site analytics counters (Req 27.1).
SITE_ANALYTICS_KEY = "site_analytics"
_DEFAULT_SITE_ANALYTICS: dict[str, Any] = {
    "page_views": 0,
    "visitors": 0,
    "sessions": 0,
}

# Referral-fraud heuristic: a referrer with more confirmed referrals than this
# in total is flagged for review (Req 26.4). Conservative default; the real
# threshold can later move into platform_settings.
_HIGH_VOLUME_REFERRAL_THRESHOLD = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise ValidationError("Invalid identifier", error_code="invalid_id") from exc


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(
            "Value must be a number", error_code="invalid_number"
        ) from exc


def _normalize_category(category: str) -> str:
    normalized = (category or "").strip().lower()
    if normalized not in TEMPLATE_CATEGORIES:
        raise ValidationError(
            f"Unknown template category: {category!r}",
            error_code="invalid_template_category",
        )
    return normalized


# ---------------------------------------------------------------------------
# Coupon CRUD (Req 26)
# ---------------------------------------------------------------------------
def serialize_coupon(coupon: Coupon) -> dict[str, Any]:
    return {
        "id": str(coupon.id),
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "value": _as_decimal(coupon.value),
        "max_redemptions": coupon.max_redemptions,
        "redemptions": coupon.redemptions,
        "valid_until": coupon.valid_until.isoformat()
        if coupon.valid_until is not None
        else None,
        "active": coupon.active,
    }


async def create_coupon(
    session: AsyncSession,
    *,
    code: str,
    discount_type: str,
    value: Any,
    max_redemptions: Optional[int] = None,
    valid_until: Optional[datetime.datetime] = None,
    active: bool = True,
) -> Coupon:
    """Create a discount coupon (Req 26).

    Rejects a blank/duplicate code, an unknown discount type, or a negative
    value. ``percent`` coupons are additionally capped at 100.
    """
    normalized_code = (code or "").strip()
    if not normalized_code:
        raise ValidationError("Coupon code is required", error_code="coupon_code_empty")

    normalized_type = (discount_type or "").strip().lower()
    if normalized_type not in COUPON_DISCOUNT_TYPES:
        raise ValidationError(
            f"Unknown discount type: {discount_type!r}",
            error_code="invalid_discount_type",
        )

    value_dec = _as_decimal(value)
    if value_dec < 0:
        raise ValidationError(
            "Coupon value must be non-negative", error_code="invalid_coupon_value"
        )
    if normalized_type == "percent" and value_dec > 100:
        raise ValidationError(
            "Percent discount cannot exceed 100",
            error_code="invalid_coupon_value",
        )
    if max_redemptions is not None and max_redemptions < 0:
        raise ValidationError(
            "max_redemptions must be non-negative",
            error_code="invalid_max_redemptions",
        )

    existing = (
        await session.execute(select(Coupon.id).where(Coupon.code == normalized_code))
    ).first()
    if existing is not None:
        raise ValidationError(
            "A coupon with this code already exists",
            error_code="coupon_code_exists",
        )

    coupon = Coupon(
        code=normalized_code,
        discount_type=normalized_type,
        value=value_dec,
        max_redemptions=max_redemptions,
        valid_until=valid_until,
        active=active,
    )
    session.add(coupon)
    await session.commit()
    await session.refresh(coupon)
    logger.info("coupon_created", extra={"coupon_id": str(coupon.id)})
    return coupon


async def list_coupons(session: AsyncSession) -> list[Coupon]:
    """List all coupons, newest first."""
    rows = (
        await session.execute(select(Coupon).order_by(Coupon.created_at.desc()))
    ).scalars().all()
    return list(rows)


async def get_coupon(session: AsyncSession, coupon_id: Any) -> Coupon:
    coupon = await session.get(Coupon, _to_uuid(coupon_id))
    if coupon is None:
        raise NotFoundError("Coupon not found", error_code="coupon_not_found")
    return coupon


async def update_coupon(
    session: AsyncSession,
    coupon_id: Any,
    *,
    discount_type: Optional[str] = None,
    value: Any = None,
    max_redemptions: Any = None,
    valid_until: Any = None,
    active: Optional[bool] = None,
) -> Coupon:
    """Update mutable fields of a coupon (Req 26).

    Only supplied fields are changed. The unique ``code`` is intentionally not
    editable so existing redemptions/subscriptions keep referring to the same
    coupon identity.
    """
    coupon = await get_coupon(session, coupon_id)

    if discount_type is not None:
        normalized_type = discount_type.strip().lower()
        if normalized_type not in COUPON_DISCOUNT_TYPES:
            raise ValidationError(
                f"Unknown discount type: {discount_type!r}",
                error_code="invalid_discount_type",
            )
        coupon.discount_type = normalized_type

    if value is not None:
        value_dec = _as_decimal(value)
        if value_dec < 0:
            raise ValidationError(
                "Coupon value must be non-negative",
                error_code="invalid_coupon_value",
            )
        if coupon.discount_type == "percent" and value_dec > 100:
            raise ValidationError(
                "Percent discount cannot exceed 100",
                error_code="invalid_coupon_value",
            )
        coupon.value = value_dec

    if max_redemptions is not None:
        if max_redemptions < 0:
            raise ValidationError(
                "max_redemptions must be non-negative",
                error_code="invalid_max_redemptions",
            )
        coupon.max_redemptions = max_redemptions

    if valid_until is not None:
        coupon.valid_until = valid_until

    if active is not None:
        coupon.active = active

    await session.commit()
    await session.refresh(coupon)
    logger.info("coupon_updated", extra={"coupon_id": str(coupon.id)})
    return coupon


async def delete_coupon(session: AsyncSession, coupon_id: Any) -> None:
    """Delete a coupon (Req 26)."""
    coupon = await get_coupon(session, coupon_id)
    await session.delete(coupon)
    await session.commit()
    logger.info("coupon_deleted", extra={"coupon_id": str(coupon_id)})


# ---------------------------------------------------------------------------
# Per-partner commission override (Req 26.1, 26.2)
# ---------------------------------------------------------------------------
async def set_commission_override(
    session: AsyncSession,
    org_id: Any,
    *,
    rate: Any,
) -> Organization:
    """Set (or clear) a partner's commission override (Req 26.1, 26.2).

    A numeric ``rate`` - *including zero* - is stored as the organization's
    ``commission_rate_override`` and applied to that partner in place of the
    ₹50 default (Req 26.2). A configured zero is an explicit "no commission"
    setting, not the unset state, so it is honoured (Req 26.1). Passing ``None``
    clears the override, returning the partner to the default rate.

    A negative rate is rejected to uphold the ``commissions.amount >= 0``
    invariant.
    """
    org = await session.get(Organization, _to_uuid(org_id))
    if org is None:
        raise NotFoundError("Organization not found", error_code="org_not_found")

    if rate is None:
        org.commission_rate_override = None
    else:
        rate_dec = _as_decimal(rate)
        if rate_dec < 0:
            raise ValidationError(
                "Commission rate must be non-negative",
                error_code="invalid_commission_rate",
            )
        org.commission_rate_override = rate_dec

    await session.commit()
    await session.refresh(org)
    logger.info(
        "commission_override_set",
        extra={"org_id": str(org.id), "rate": str(org.commission_rate_override)},
    )
    return org


# ---------------------------------------------------------------------------
# Referral tracking with fraud flags (Req 26.4)
# ---------------------------------------------------------------------------
async def list_referrals_with_fraud_flags(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return referral records annotated with fraud flags (Req 26.4).

    Fraud heuristics flagged per record:

    - ``self_referral``: the referred user is the referrer.
    - ``duplicate_gmail``: the referred Gmail identity appears on more than one
      referral record (one-account-per-Gmail abuse, Req 19.6).
    - ``high_volume_referrer``: the referrer has more confirmed referrals than
      the configured threshold (possible farming).

    ``fraud`` is the OR of the individual flags so the admin UI can highlight
    suspicious rows at a glance.
    """
    referrals = (
        await session.execute(select(Referral).order_by(Referral.created_at.desc()))
    ).scalars().all()

    # Count duplicate referred_gmail values across all referral records.
    gmail_counts: dict[str, int] = {}
    referrer_counts: dict[uuid.UUID, int] = {}
    for r in referrals:
        if r.referred_gmail:
            gmail_counts[r.referred_gmail] = gmail_counts.get(r.referred_gmail, 0) + 1
        if r.status == "confirmed":
            referrer_counts[r.referrer_user_id] = (
                referrer_counts.get(r.referrer_user_id, 0) + 1
            )

    results: list[dict[str, Any]] = []
    for r in referrals:
        self_referral = (
            r.referred_user_id is not None
            and r.referred_user_id == r.referrer_user_id
        )
        duplicate_gmail = bool(r.referred_gmail) and gmail_counts.get(
            r.referred_gmail, 0
        ) > 1
        high_volume = (
            referrer_counts.get(r.referrer_user_id, 0)
            > _HIGH_VOLUME_REFERRAL_THRESHOLD
        )
        flags = {
            "self_referral": self_referral,
            "duplicate_gmail": duplicate_gmail,
            "high_volume_referrer": high_volume,
        }
        results.append(
            {
                "id": str(r.id),
                "referrer_user_id": str(r.referrer_user_id),
                "referred_user_id": str(r.referred_user_id)
                if r.referred_user_id is not None
                else None,
                "referred_gmail": r.referred_gmail,
                "status": r.status,
                "created_at": r.created_at.isoformat()
                if r.created_at is not None
                else None,
                "fraud_flags": flags,
                "fraud": any(flags.values()),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Template CRUD (Req 27.2)
# ---------------------------------------------------------------------------
def serialize_template(template: Template) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "category": template.category,
        "name": template.name,
        "arduino_code": template.arduino_code,
        "wiring_diagram_url": template.wiring_diagram_url,
        "dashboard_def": template.dashboard_def,
        "rules_def": template.rules_def,
    }


async def create_template(
    session: AsyncSession,
    *,
    category: str,
    name: str,
    arduino_code: Optional[str] = None,
    wiring_diagram_url: Optional[str] = None,
    dashboard_def: Optional[dict] = None,
    rules_def: Optional[dict] = None,
) -> Template:
    """Create a student/company template in the global catalog (Req 27.2)."""
    normalized_category = _normalize_category(category)
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValidationError(
            "Template name is required", error_code="template_name_empty"
        )

    template = Template(
        category=normalized_category,
        name=normalized_name,
        arduino_code=arduino_code,
        wiring_diagram_url=wiring_diagram_url,
        dashboard_def=dashboard_def,
        rules_def=rules_def,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    logger.info("template_created", extra={"template_id": str(template.id)})
    return template


async def update_template(
    session: AsyncSession,
    template_id: Any,
    *,
    category: Optional[str] = None,
    name: Optional[str] = None,
    arduino_code: Any = _UNSET,
    wiring_diagram_url: Any = _UNSET,
    dashboard_def: Any = _UNSET,
    rules_def: Any = _UNSET,
) -> Template:
    """Edit a template; only fields explicitly supplied are changed (Req 27.2)."""
    template = await session.get(Template, _to_uuid(template_id))
    if template is None:
        raise NotFoundError("Template not found", error_code="template_not_found")

    if category is not None:
        template.category = _normalize_category(category)
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError(
                "Template name is required", error_code="template_name_empty"
            )
        template.name = normalized_name
    if arduino_code is not _UNSET:
        template.arduino_code = arduino_code
    if wiring_diagram_url is not _UNSET:
        template.wiring_diagram_url = wiring_diagram_url
    if dashboard_def is not _UNSET:
        template.dashboard_def = dashboard_def
    if rules_def is not _UNSET:
        template.rules_def = rules_def

    await session.commit()
    await session.refresh(template)
    logger.info("template_updated", extra={"template_id": str(template.id)})
    return template


async def delete_template(session: AsyncSession, template_id: Any) -> None:
    """Delete a template from the catalog (Req 27.2)."""
    template = await session.get(Template, _to_uuid(template_id))
    if template is None:
        raise NotFoundError("Template not found", error_code="template_not_found")
    await session.delete(template)
    await session.commit()
    logger.info("template_deleted", extra={"template_id": str(template_id)})


# ---------------------------------------------------------------------------
# Notification settings (Req 27.3)
# ---------------------------------------------------------------------------
async def get_notification_settings() -> dict[str, Any]:
    """Return the platform Telegram/push/email notification settings (Req 27.3)."""
    value = await get_setting(
        NOTIFICATION_SETTINGS_KEY, default=_DEFAULT_NOTIFICATION_SETTINGS
    )
    if not isinstance(value, dict):
        return dict(_DEFAULT_NOTIFICATION_SETTINGS)
    # Merge over defaults so unset channels still report their shape.
    merged = {k: dict(v) for k, v in _DEFAULT_NOTIFICATION_SETTINGS.items()}
    for channel, conf in value.items():
        if channel in merged and isinstance(conf, dict):
            merged[channel].update(conf)
        else:
            merged[channel] = conf
    return merged


async def update_notification_settings(
    *,
    telegram: Optional[dict] = None,
    push: Optional[dict] = None,
    email: Optional[dict] = None,
) -> dict[str, Any]:
    """Apply Telegram/push/email notification settings platform-wide (Req 27.3).

    Only the channels supplied are updated; the change is persisted through the
    settings loader so it takes effect immediately for notification delivery
    (Req 29.4 mechanism).
    """
    current = await get_notification_settings()
    if telegram is not None:
        current["telegram"] = {**current.get("telegram", {}), **telegram}
    if push is not None:
        current["push"] = {**current.get("push", {}), **push}
    if email is not None:
        current["email"] = {**current.get("email", {}), **email}

    await set_setting(NOTIFICATION_SETTINGS_KEY, current)
    logger.info("notification_settings_updated")
    return current


# ---------------------------------------------------------------------------
# Site analytics (Req 27.1)
# ---------------------------------------------------------------------------
async def get_site_analytics() -> dict[str, Any]:
    """Return site analytics: page views, visitors, sessions (Req 27.1)."""
    value = await get_setting(SITE_ANALYTICS_KEY, default=_DEFAULT_SITE_ANALYTICS)
    if not isinstance(value, dict):
        return dict(_DEFAULT_SITE_ANALYTICS)
    return {**_DEFAULT_SITE_ANALYTICS, **value}
