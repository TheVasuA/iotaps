"""Volume discount pricing engine (Task 14.3, Req 16).

Single source of truth for Pro_Plan pricing math, mirroring design.md
("Volume Discount Pricing"):

    unit_price_monthly(device_count):
        1-10   -> ₹99
        11-50  -> ₹79
        51-200 -> ₹69
        201+   -> ₹59
    annual: a fixed ₹948 per Device per year (Req 16.1, 16.7).

The tier applies to the whole purchase based on its device-count band; the
boundaries (10/11, 50/51, 200/201) are exact (Req 16.6). Per-device monthly
price is non-increasing as the device count grows (Property 10).

All amounts are whole rupees and represented as ``int`` - the published prices
are integers, so there is no sub-rupee rounding to reason about. The pricing
functions here are pure (no DB/Redis/Razorpay), which keeps them trivially
testable and lets the billing router, the Razorpay subscribe flow (Task 15.1),
and the frontend quote mirror (Task 14.5) all agree on one calculation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import ValidationError
from app.services.plan_limits import FREE_LIMITS, PRO_LIMITS

# Billing cycle identifiers (subscriptions.billing_cycle).
CYCLE_MONTHLY = "monthly"
CYCLE_YEARLY = "yearly"

# Fixed annual price per device (Req 16.1, 16.7).
ANNUAL_UNIT_PRICE = 948


@dataclass(frozen=True)
class PricingTier:
    """One volume-discount band for the monthly Pro_Plan price (Req 16.2-16.5).

    ``max_devices`` is ``None`` for the open-ended top tier (201+ devices).
    """

    min_devices: int
    max_devices: int | None
    unit_price_monthly: int


# Ordered from smallest band to the open-ended top tier (Req 16.2-16.5). The
# order matters: ``unit_price_monthly`` walks these and returns the first match.
PRICING_TIERS: tuple[PricingTier, ...] = (
    PricingTier(min_devices=1, max_devices=10, unit_price_monthly=99),
    PricingTier(min_devices=11, max_devices=50, unit_price_monthly=79),
    PricingTier(min_devices=51, max_devices=200, unit_price_monthly=69),
    PricingTier(min_devices=201, max_devices=None, unit_price_monthly=59),
)


def _validate_device_count(device_count: int) -> int:
    """Coerce/validate ``device_count`` to a positive integer (>= 1)."""
    if isinstance(device_count, bool) or not isinstance(device_count, int):
        raise ValidationError("device_count must be an integer")
    if device_count < 1:
        raise ValidationError("device_count must be at least 1")
    return device_count


def normalize_cycle(billing_cycle: str) -> str:
    """Resolve a billing cycle string to ``monthly``/``yearly`` (case-insensitive)."""
    if isinstance(billing_cycle, str):
        normalized = billing_cycle.strip().lower()
        if normalized in (CYCLE_MONTHLY, CYCLE_YEARLY):
            return normalized
    raise ValidationError("billing_cycle must be 'monthly' or 'yearly'")


def unit_price_monthly(device_count: int) -> int:
    """Per-device monthly price for a purchase of ``device_count`` devices.

    Returns the rate for the volume tier the device count falls in
    (Req 16.2-16.5); the band boundaries are exact (Req 16.6).
    """
    device_count = _validate_device_count(device_count)
    for tier in PRICING_TIERS:
        if tier.max_devices is None or device_count <= tier.max_devices:
            return tier.unit_price_monthly
    # Unreachable: the final tier is open-ended, but keep a defensive default.
    return PRICING_TIERS[-1].unit_price_monthly


def unit_price(device_count: int, billing_cycle: str) -> int:
    """Per-device price for the given cycle.

    Yearly is the fixed ₹948/device (Req 16.1, 16.7); monthly uses the volume
    tier rate (Req 16.2-16.5).
    """
    cycle = normalize_cycle(billing_cycle)
    device_count = _validate_device_count(device_count)
    if cycle == CYCLE_YEARLY:
        return ANNUAL_UNIT_PRICE
    return unit_price_monthly(device_count)


def total(device_count: int, billing_cycle: str) -> int:
    """Total purchase price = per-device price x device count (Req 16.6, 16.7)."""
    device_count = _validate_device_count(device_count)
    return device_count * unit_price(device_count, billing_cycle)


def quote(device_count: int, billing_cycle: str) -> dict:
    """Build a pricing quote for ``device_count`` devices on ``billing_cycle``.

    Returns ``{device_count, billing_cycle, unit_price, total}`` as plain ints
    so the router and the frontend mirror share one shape (design.md
    POST /billing/quote -> {unit_price, total}).
    """
    cycle = normalize_cycle(billing_cycle)
    device_count = _validate_device_count(device_count)
    per_device = unit_price(device_count, cycle)
    return {
        "device_count": device_count,
        "billing_cycle": cycle,
        "unit_price": per_device,
        "total": device_count * per_device,
    }


def pricing_tiers() -> list[dict]:
    """Serialise the monthly volume-discount tiers for GET /billing/plans."""
    return [
        {
            "min_devices": tier.min_devices,
            "max_devices": tier.max_devices,
            "unit_price_monthly": tier.unit_price_monthly,
        }
        for tier in PRICING_TIERS
    ]


def plans() -> dict:
    """Describe the Free and Pro plans plus the volume tiers (GET /billing/plans).

    Plan entitlements are sourced from :mod:`app.services.plan_limits` so the
    advertised limits stay in lockstep with what the platform actually enforces
    (Req 15.1, 15.2). ``None`` numeric limits denote "unlimited" (Pro).
    """
    return {
        "free": {
            "plan": FREE_LIMITS.plan,
            "max_devices": FREE_LIMITS.max_devices,
            "max_messages_per_month": FREE_LIMITS.max_messages_per_month,
            "retention_days": FREE_LIMITS.retention_days,
            "max_sensors": FREE_LIMITS.max_sensors,
            "max_rules": FREE_LIMITS.max_rules,
            "full_control": FREE_LIMITS.full_control,
        },
        "pro": {
            "plan": PRO_LIMITS.plan,
            "max_devices": PRO_LIMITS.max_devices,
            "max_messages_per_month": PRO_LIMITS.max_messages_per_month,
            "retention_days": PRO_LIMITS.retention_days,
            "max_sensors": PRO_LIMITS.max_sensors,
            "max_rules": PRO_LIMITS.max_rules,
            "full_control": PRO_LIMITS.full_control,
            "unit_price_monthly": PRICING_TIERS[0].unit_price_monthly,
            "annual_unit_price": ANNUAL_UNIT_PRICE,
        },
        "pricing_tiers": pricing_tiers(),
    }
