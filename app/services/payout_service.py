"""Partner payout request & approval (Task 16.3, Req 18.4-18.6, 26.3).

Implements the design's "Payout (never exceeds balance)" algorithm
(design.md "Billing, Partner, Referral"):

    def request_payout(org, amount, dest):
        wallet = lock_wallet(org)
        if amount > wallet.balance: reject("insufficient")   # 18.6
        create payout(PENDING, amount, dest)
    def approve_payout(payout):
        wallet = lock_wallet(payout.org)
        if payout.amount > wallet.balance: reject()          # re-check at approval
        wallet.balance -= payout.amount                      # stays >= 0
        payout.status = APPROVED
        razorpayx.transfer(dest, amount); payout.status = PAID

Two halves with different trust boundaries:

- **Request** (Project_Center, tenant-scoped). A partner asks to withdraw a
  rupee ``amount`` to a ``destination`` (bank/UPI). The request is rejected up
  front when it exceeds the available Partner_Wallet balance (Req 18.6); an
  acceptable request is persisted as a ``PENDING`` payout. The wallet is *not*
  debited yet - the money only moves on Super_Admin approval.
- **Approval** (Super_Admin, cross-org). The balance is re-checked at approval
  time because other payouts/commissions may have changed it since the request
  (the design's "re-check at approval"). On success the wallet is debited by
  exactly the payout amount - keeping ``balance >= 0`` (the wallet invariant) -
  the status is set to ``APPROVED``, the funds are transferred via RazorpayX
  (mocked/offline in tests, Req 18.5), and the status advances to ``PAID`` with
  the RazorpayX payout id recorded (Req 26.3).

All wallet arithmetic uses :class:`~decimal.Decimal` so the NUMERIC balance
stays exact (no binary-float drift), mirroring
:mod:`app.services.commission_service`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.billing import Commission, PartnerWallet, Payout
from app.services.razorpay_client import PAISE_PER_RUPEE, RazorpayXClient

logger = get_logger(__name__)

# Payout status values (mirror design.md Table Catalog: payouts.status).
PAYOUT_PENDING = "PENDING"
PAYOUT_APPROVED = "APPROVED"
PAYOUT_REJECTED = "REJECTED"
PAYOUT_PAID = "PAID"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_decimal(value: Any) -> Decimal:
    """Convert a NUMERIC/`float`/`int`/`str` value to ``Decimal`` safely."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_uuid(value: Any) -> uuid.UUID:
    """Coerce a value to ``uuid.UUID`` (raises ValueError if not coercible)."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def _get_wallet_for_org(
    session: AsyncSession, org_id: uuid.UUID
) -> Optional[PartnerWallet]:
    """Fetch the org's Partner_Wallet (one per org), or ``None`` if absent."""
    result = await session.execute(
        select(PartnerWallet).where(PartnerWallet.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def request_payout(
    session: AsyncSession,
    *,
    org_id: Any,
    amount: Any,
    destination: Optional[str] = None,
) -> Payout:
    """Create a PENDING payout request, rejecting an over-balance amount (Req 18.4, 18.6).

    Resolves the requesting org's Partner_Wallet and rejects the request when
    ``amount`` exceeds the available balance (Req 18.6) - the wallet is left
    untouched. An acceptable request is persisted as a ``PENDING`` payout for
    Super_Admin approval (Req 18.4); the balance is only debited at approval.

    Args:
        session: active async DB session (this function commits the new payout).
        org_id: the Project_Center requesting the withdrawal.
        amount: the rupee amount to withdraw (must be > 0).
        destination: bank/UPI destination string for the transfer.

    Returns:
        The persisted ``PENDING`` :class:`Payout`.

    Raises:
        ValidationError: if ``amount`` is not positive, or exceeds the balance.
        NotFoundError: if the org has no Partner_Wallet (no commission earned).
    """
    org_uuid = _to_uuid(org_id)
    amount_dec = _as_decimal(amount)

    if amount_dec <= 0:
        raise ValidationError(
            "Payout amount must be greater than zero",
            error_code="invalid_payout_amount",
        )

    wallet = await _get_wallet_for_org(session, org_uuid)
    if wallet is None:
        # No wallet means no earned commission to withdraw against.
        raise NotFoundError(
            "No partner wallet found for this organization",
            error_code="wallet_not_found",
        )

    balance = _as_decimal(wallet.balance)
    if amount_dec > balance:
        # Insufficient funds: reject up front, wallet untouched (Req 18.6).
        raise ValidationError(
            "Payout amount exceeds the available wallet balance",
            error_code="insufficient_balance",
        )

    payout = Payout(
        org_id=org_uuid,
        wallet_id=wallet.id,
        amount=amount_dec,
        destination=destination,
        status=PAYOUT_PENDING,
        requested_at=_now(),
    )
    session.add(payout)
    await session.commit()
    await session.refresh(payout)
    logger.info(
        "partner_payout_requested",
        extra={"payout_id": str(payout.id), "org_id": str(org_uuid)},
    )
    return payout


async def approve_payout(
    session: AsyncSession,
    *,
    payout_id: Any,
    approved_by: Any | None = None,
    razorpayx: Optional[RazorpayXClient] = None,
) -> Payout:
    """Approve a PENDING payout: debit wallet, transfer, set APPROVED then PAID.

    Re-checks the wallet balance at approval time (the balance may have changed
    since the request) and rejects when the amount now exceeds it. On success
    the wallet is debited by exactly the payout amount - keeping ``balance >= 0``
    - the status is set to ``APPROVED`` and the funds are transferred via
    RazorpayX (mocked/offline, Req 18.5); the status then advances to ``PAID``
    with the RazorpayX payout id recorded (Req 18.5, 26.3).

    Args:
        session: active async DB session (this function commits the transition).
        payout_id: the payout to approve.
        approved_by: the Super_Admin user id recorded as the approver.
        razorpayx: the RazorpayX client used for the transfer (offline default).

    Returns:
        The persisted ``PAID`` :class:`Payout`.

    Raises:
        NotFoundError: if the payout or its wallet does not exist.
        ValidationError: if the payout is not PENDING, or the amount now exceeds
            the available balance.
    """
    razorpayx = razorpayx or RazorpayXClient()
    payout = await session.get(Payout, _to_uuid(payout_id))
    if payout is None:
        raise NotFoundError("Payout not found", error_code="payout_not_found")

    if payout.status != PAYOUT_PENDING:
        raise ValidationError(
            f"Only a PENDING payout can be approved (current status: {payout.status})",
            error_code="payout_not_pending",
        )

    wallet = await session.get(PartnerWallet, payout.wallet_id)
    if wallet is None:
        raise NotFoundError(
            "Partner wallet not found for payout",
            error_code="wallet_not_found",
        )

    amount = _as_decimal(payout.amount)
    balance = _as_decimal(wallet.balance)
    if amount > balance:
        # Balance moved below the requested amount since the request was made:
        # re-check at approval guards the wallet invariant (design.md).
        raise ValidationError(
            "Payout amount exceeds the available wallet balance",
            error_code="insufficient_balance",
        )

    # Debit first so the wallet stays >= 0; the credited amount equals the
    # payout amount exactly (Req 18.5, balance >= 0 invariant).
    wallet.balance = balance - amount
    payout.status = PAYOUT_APPROVED
    payout.approved_at = _now()
    if approved_by is not None:
        payout.approved_by = _to_uuid(approved_by)

    # Transfer via RazorpayX (offline/mocked in tests; no live secret needed).
    transfer = razorpayx.transfer(
        amount=int(amount) * PAISE_PER_RUPEE,
        destination=payout.destination,
    )
    payout.razorpayx_payout_id = transfer.id
    payout.status = PAYOUT_PAID

    await session.commit()
    await session.refresh(payout)
    logger.info(
        "partner_payout_approved",
        extra={
            "payout_id": str(payout.id),
            "razorpayx_payout_id": transfer.id,
            "status": payout.status,
        },
    )
    return payout


async def get_wallet_summary(
    session: AsyncSession, org_id: Any
) -> dict[str, Any]:
    """Return the org's wallet balance and its commission history (Req 18.4).

    A partner with no wallet yet (no earned commission) reports a zero balance
    and an empty commission list rather than an error.
    """
    org_uuid = _to_uuid(org_id)
    wallet = await _get_wallet_for_org(session, org_uuid)
    if wallet is None:
        return {"balance": 0, "commissions": []}

    result = await session.execute(
        select(Commission)
        .where(Commission.wallet_id == wallet.id)
        .order_by(Commission.created_at.desc())
    )
    commissions = result.scalars().all()
    return {
        "balance": _as_decimal(wallet.balance),
        "commissions": [
            {
                "id": str(c.id),
                "amount": _as_decimal(c.amount),
                "device_id": str(c.device_id) if c.device_id is not None else None,
                "payment_id": str(c.payment_id) if c.payment_id is not None else None,
                "period_month": c.period_month.isoformat()
                if c.period_month is not None
                else None,
            }
            for c in commissions
        ],
    }
