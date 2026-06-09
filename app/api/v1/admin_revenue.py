"""Admin revenue analytics API (Task 20.3, Req 25.1, 25.2).

Exposes the Super_Admin revenue dashboard from design.md ("Admin"):

    GET /admin/revenue -> {mrr, arr, churn, funnel, arpu, by_source, top_orgs}

Super_Admin-only (Req 2.5, 25): the metrics span every organization, so the
route is gated by ``require_role(ROLE_SUPER_ADMIN)`` and reads the request
session directly rather than the tenant-filtered scope. Every figure is
computed on demand by :mod:`app.services.revenue_service` from the current
``subscriptions``/``payments``/``organizations`` rows, so the response always
reflects the latest billing or subscription data the moment it is recorded
(Req 25.2).

This lives in its own module (and its own ``APIRouter``) to keep the admin
surface modular; it is registered in the v1 aggregate router alongside the
other admin routers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.services import revenue_service

router = APIRouter(prefix="/admin", tags=["admin", "revenue"])


# ---------------------------------------------------------------------------
# Schemas (mirror design.md GET /admin/revenue shape)
# ---------------------------------------------------------------------------
class FunnelOut(BaseModel):
    organizations: int
    with_subscription: int
    paying: int
    conversion_rate: float


class TopOrgOut(BaseModel):
    org_id: str
    name: str
    revenue: float


class RevenueAnalyticsOut(BaseModel):
    mrr: float
    arr: float
    churn: float
    funnel: FunnelOut
    arpu: float
    by_source: dict[str, float]
    top_orgs: list[TopOrgOut]


@router.get("/revenue", response_model=RevenueAnalyticsOut)
async def get_revenue_analytics(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> RevenueAnalyticsOut:
    """Return platform revenue analytics for the Super_Admin (Req 25.1, 25.2).

    Computes MRR, ARR, churn, the conversion funnel, ARPU, revenue by source,
    and the top organizations by revenue live from current billing data, so the
    response updates as new billing/subscription data is recorded.
    """
    analytics = await revenue_service.compute_revenue_analytics(session)
    return RevenueAnalyticsOut(**analytics)
