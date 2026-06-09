"""Admin revenue analytics (Task 20.3, Req 25.1, 25.2).

Computes the Super_Admin revenue dashboard metrics from design.md
(GET /admin/revenue -> {mrr, arr, churn, funnel, arpu, by_source, top_orgs})
directly from the *current* billing/subscription state. Because every metric is
derived on demand from ``subscriptions``/``payments``/``organizations`` rather
than a precomputed snapshot, the figures always reflect the latest billing or
subscription data the moment it is recorded (Req 25.2).

Metric definitions
------------------
- **MRR** (Monthly Recurring Revenue): the monthly-normalised value of every
  ``active`` subscription. A monthly subscription contributes
  ``device_count * unit_price``; a yearly subscription contributes that line
  divided by 12 so annual contracts are comparable to monthly ones.
- **ARR** (Annual Recurring Revenue): ``MRR * 12``.
- **churn**: the share of all subscriptions ever created that are now
  ``cancelled`` (``cancelled / total``); 0 when there are no subscriptions.
- **funnel** (conversion funnel): organization counts down the monetisation
  path - total organizations -> organizations with any subscription ->
  organizations with an active subscription - plus the resulting conversion
  rate (paying / total).
- **arpu** (average revenue per paying account): ``MRR`` spread across the
  organizations with an active subscription; 0 when there are none.
- **by_source**: captured-payment revenue grouped by billing cycle
  (``monthly`` / ``yearly`` / ``unknown``), i.e. where realised money came from.
- **top_orgs**: the organizations with the highest realised (captured) revenue,
  with id, name, and total, highest first.

All money math uses :class:`~decimal.Decimal` so NUMERIC columns stay exact,
then results are rounded to whole paise (2 dp) and returned as ``float`` for a
plain JSON response. The functions read through the request session directly
(not the tenant-filtered ``scope.select``) because revenue analytics span every
organization and the route is Super_Admin-only (Req 2.5, 23/25).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Payment, Subscription
from app.models.organization import Organization
from app.services import billing_service

# Subscription lifecycle states that count as live recurring revenue / churn.
SUB_STATUS_ACTIVE = "active"
SUB_STATUS_CANCELLED = "cancelled"

# Payment status that represents realised money (mirrors subscription_service).
PAY_STATUS_CAPTURED = "captured"

# How many top organizations to surface in the revenue leaderboard.
TOP_ORGS_LIMIT = 10

_CENTS = Decimal("0.01")
_MONTHS_PER_YEAR = Decimal(12)


def _as_decimal(value: Any) -> Decimal:
    """Convert a NUMERIC/``float``/``int``/``str``/``None`` value to ``Decimal``."""
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> float:
    """Round a ``Decimal`` to 2 dp (paise) and return it as a JSON-friendly float."""
    return float(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


def _monthly_value(subscription: Subscription) -> Decimal:
    """Monthly-normalised revenue for one subscription line.

    ``device_count * unit_price`` for a monthly cycle; the same divided by 12
    for a yearly cycle so annual contracts are comparable to monthly MRR.
    Missing counts/prices contribute nothing.
    """
    device_count = _as_decimal(subscription.device_count)
    unit_price = _as_decimal(subscription.unit_price)
    line = device_count * unit_price
    if subscription.billing_cycle == billing_service.CYCLE_YEARLY:
        return line / _MONTHS_PER_YEAR
    return line


async def compute_revenue_analytics(session: AsyncSession) -> dict[str, Any]:
    """Compute the full revenue analytics payload from current data (Req 25.1, 25.2).

    Returns ``{mrr, arr, churn, funnel, arpu, by_source, top_orgs}`` derived
    live from ``subscriptions``/``payments``/``organizations`` so it reflects
    the latest billing data on every call.
    """
    mrr, paying_org_count = await _mrr_and_paying_orgs(session)
    arr = mrr * _MONTHS_PER_YEAR
    arpu = mrr / paying_org_count if paying_org_count else Decimal(0)

    return {
        "mrr": _money(mrr),
        "arr": _money(arr),
        "arpu": _money(arpu),
        "churn": await _churn_rate(session),
        "funnel": await _conversion_funnel(session, paying_org_count),
        "by_source": await _revenue_by_source(session),
        "top_orgs": await _top_orgs_by_revenue(session),
    }


async def _mrr_and_paying_orgs(session: AsyncSession) -> tuple[Decimal, int]:
    """MRR over all active subscriptions, plus the distinct paying-org count."""
    result = await session.execute(
        select(Subscription).where(Subscription.status == SUB_STATUS_ACTIVE)
    )
    subscriptions = result.scalars().all()
    mrr = sum((_monthly_value(s) for s in subscriptions), Decimal(0))
    paying_orgs = {s.org_id for s in subscriptions}
    return mrr, len(paying_orgs)


async def _churn_rate(session: AsyncSession) -> float:
    """Cancelled subscriptions as a fraction of all subscriptions (0 if none)."""
    total = await session.scalar(select(func.count()).select_from(Subscription)) or 0
    if not total:
        return 0.0
    cancelled = (
        await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SUB_STATUS_CANCELLED)
        )
        or 0
    )
    return float((Decimal(cancelled) / Decimal(total)).quantize(Decimal("0.0001")))


async def _conversion_funnel(
    session: AsyncSession, paying_org_count: int
) -> dict[str, Any]:
    """Organization counts down the monetisation path + conversion rate."""
    total_orgs = (
        await session.scalar(select(func.count()).select_from(Organization)) or 0
    )
    orgs_with_subscription = (
        await session.scalar(
            select(func.count(func.distinct(Subscription.org_id)))
        )
        or 0
    )
    conversion_rate = (
        float((Decimal(paying_org_count) / Decimal(total_orgs)).quantize(Decimal("0.0001")))
        if total_orgs
        else 0.0
    )
    return {
        "organizations": int(total_orgs),
        "with_subscription": int(orgs_with_subscription),
        "paying": int(paying_org_count),
        "conversion_rate": conversion_rate,
    }


async def _revenue_by_source(session: AsyncSession) -> dict[str, float]:
    """Captured-payment revenue grouped by subscription billing cycle."""
    result = await session.execute(
        select(
            Subscription.billing_cycle,
            func.sum(Payment.amount),
        )
        .select_from(Payment)
        .join(Subscription, Payment.subscription_id == Subscription.id, isouter=True)
        .where(Payment.status == PAY_STATUS_CAPTURED)
        .group_by(Subscription.billing_cycle)
    )
    by_source: dict[str, float] = {}
    for cycle, amount in result.all():
        key = cycle if cycle in (billing_service.CYCLE_MONTHLY, billing_service.CYCLE_YEARLY) else "unknown"
        by_source[key] = _money(_as_decimal(by_source.get(key, 0)) + _as_decimal(amount))
    return by_source


async def _top_orgs_by_revenue(session: AsyncSession) -> list[dict[str, Any]]:
    """Top organizations by realised (captured) revenue, highest first."""
    revenue = func.sum(Payment.amount).label("revenue")
    result = await session.execute(
        select(Organization.id, Organization.name, revenue)
        .select_from(Payment)
        .join(Organization, Payment.org_id == Organization.id)
        .where(Payment.status == PAY_STATUS_CAPTURED)
        .group_by(Organization.id, Organization.name)
        .order_by(revenue.desc())
        .limit(TOP_ORGS_LIMIT)
    )
    return [
        {
            "org_id": str(org_id),
            "name": name,
            "revenue": _money(_as_decimal(amount)),
        }
        for org_id, name, amount in result.all()
    ]
