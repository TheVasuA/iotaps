"""Partner wallet & payout API (Task 16.3, Req 18.4-18.6, 26.3).

Implements the partner-facing payout surface plus the Super_Admin approval
route from design.md ("Billing, Partner, Referral"):

    GET    /partner/wallet                 -> {balance, commissions[]}
    POST   /partner/payouts  {amount, destination} -> {payout PENDING}
    POST   /admin/payouts/{id}/approve     -> {payout PAID}

``/partner/wallet`` and ``/partner/payouts`` are tenant-scoped to the calling
Project_Center: the wallet read and the payout request both resolve the org
from the principal, so a partner only ever sees / withdraws against its own
balance. A payout request that exceeds the available balance is rejected
(Req 18.6); an acceptable one is persisted ``PENDING`` for Super_Admin approval
(Req 18.4).

``/admin/payouts/{id}/approve`` is Super_Admin-only (Req 26.3): it debits the
wallet (keeping ``balance >= 0``), sets ``APPROVED`` then transfers via
RazorpayX and sets ``PAID`` (Req 18.5). RazorpayX interaction is abstracted in
:mod:`app.services.razorpay_client` so no live API call/secret is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import (
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.services import payout_service
from app.services.razorpay_client import get_razorpayx_client

# Two routers: the partner-facing surface and the admin approval route. Both
# are registered in the v1 aggregate router.
router = APIRouter(prefix="/partner", tags=["partner"])
admin_router = APIRouter(prefix="/admin", tags=["admin", "partner"])

# Roles permitted to manage their own wallet/payouts (Super_Admin is always
# allowed by require_role; listing Project_Center documents intent).
_PARTNER_ROLES = (ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CommissionOut(BaseModel):
    id: str
    amount: Decimal
    device_id: str | None = None
    payment_id: str | None = None
    period_month: str | None = None


class WalletResponse(BaseModel):
    balance: Decimal
    commissions: list[CommissionOut]


class PayoutRequest(BaseModel):
    amount: Decimal = Field(gt=0, description="Rupee amount to withdraw")
    destination: str | None = Field(
        default=None, description="Bank/UPI destination for the transfer"
    )

    model_config = {"extra": "forbid"}


class PayoutOut(BaseModel):
    id: str
    wallet_id: str
    amount: Decimal
    destination: str | None
    status: str
    requested_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    razorpayx_payout_id: str | None


def _payout_out(payout) -> PayoutOut:
    return PayoutOut(
        id=str(payout.id),
        wallet_id=str(payout.wallet_id),
        amount=Decimal(str(payout.amount)),
        destination=payout.destination,
        status=payout.status,
        requested_at=payout.requested_at,
        approved_by=str(payout.approved_by)
        if payout.approved_by is not None
        else None,
        approved_at=payout.approved_at,
        razorpayx_payout_id=payout.razorpayx_payout_id,
    )


# ---------------------------------------------------------------------------
# Partner endpoints
# ---------------------------------------------------------------------------
@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_PARTNER_ROLES)),
) -> WalletResponse:
    """Return the caller's Partner_Wallet balance and commission history (Req 18.4)."""
    summary = await payout_service.get_wallet_summary(scope.session, scope.org_id)
    return WalletResponse(**summary)


@router.post("/payouts", response_model=PayoutOut, status_code=201)
async def request_payout(
    payload: PayoutRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_PARTNER_ROLES)),
) -> PayoutOut:
    """Request a payout, rejecting an amount over the wallet balance (Req 18.4, 18.6).

    Persists a ``PENDING`` payout for Super_Admin approval when the amount is
    within the available balance; rejects it (422) when it exceeds the balance.
    """
    payout = await payout_service.request_payout(
        scope.session,
        org_id=scope.org_id,
        amount=payload.amount,
        destination=payload.destination,
    )
    return _payout_out(payout)


# ---------------------------------------------------------------------------
# Admin approval endpoint (Req 18.5, 26.3)
# ---------------------------------------------------------------------------
@admin_router.post("/payouts/{payout_id}/approve", response_model=PayoutOut)
async def approve_payout(
    payout_id: uuid.UUID,
    principal: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    scope: TenantScope = Depends(tenant_scope),
) -> PayoutOut:
    """Approve a payout: debit wallet, transfer via RazorpayX, set PAID (Req 18.5, 26.3).

    Super_Admin-only. Re-checks the balance at approval time, debits the wallet
    (keeping ``balance >= 0``), sets ``APPROVED``, transfers the funds via
    RazorpayX (mocked/offline), and advances the status to ``PAID``.
    """
    payout = await payout_service.approve_payout(
        scope.session,
        payout_id=payout_id,
        approved_by=principal.user_id,
        razorpayx=get_razorpayx_client(),
    )
    return _payout_out(payout)
