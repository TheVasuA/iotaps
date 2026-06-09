"""Partner commission crediting (Task 16.1, Req 18.1-18.3, 26.1).

Implements the design "Partner Commission Crediting" algorithm:

    on payment.captured(device, org, period_month):
        rate = org.commission_rate_override ?? default_commission (50)
        amount = max(rate_amount(rate, device), 0)          # non-negative
        with tx:
            insert commission(org, device, payment, amount, period_month)
            update partner_wallets set balance = balance + amount where org_id=org

When a Device under a Project_Center is billed for a paid month, the partner is
credited the configured commission of ₹50 per device per month (Req 18.1). If
the Super_Admin has set a per-partner ``commission_rate_override`` on the
organization, that override is applied instead - *including a configured rate of
zero*, which is a valid "no commission" setting and must not fall back to the
default (Req 18.2, 26.1).

The credit is atomic (Req 18.3): a single transaction inserts the
``commissions`` row and increments the org's ``partner_wallets.balance`` by the
exact same amount, so the wallet balance always equals the sum of its
commissions (less payouts). The credited amount is clamped to be non-negative,
upholding the ``commissions.amount >= 0`` and ``partner_wallets.balance >= 0``
invariants (design.md Table Catalog).

This is invoked from the Razorpay webhook capture flow (Task 15.1) on a
``payment.captured`` event. The function is deliberately transport-agnostic: it
takes an :class:`AsyncSession` plus the resolved org/device/payment identifiers
so it can be called from the webhook handler or a worker without coupling to
HTTP request scope.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.billing import Commission, PartnerWallet
from app.models.organization import Organization

# Default commission credited per device per paid month when no per-partner
# override is configured (Req 18.1). Kept as Decimal so all wallet arithmetic
# stays exact (NUMERIC columns), avoiding binary-float rounding drift.
DEFAULT_COMMISSION_RATE = Decimal("50")


def _to_uuid(value: Any) -> uuid.UUID | Any:
    """Coerce a value to ``uuid.UUID`` when possible (pass through otherwise)."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return value


def _as_decimal(value: Any) -> Decimal:
    """Convert a NUMERIC/`float`/`int`/`str` value to ``Decimal`` safely."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def resolve_commission_rate(org: Organization) -> Decimal:
    """Resolve the commission rate for an organization (Req 18.1, 18.2, 26.1).

    Returns the per-partner ``commission_rate_override`` when one is set -
    *including a configured value of zero* - and otherwise the platform default
    of ₹50. A ``None`` override (the unset state) is what triggers the default;
    a zero override is honoured as an explicit "no commission" setting.
    """
    override = org.commission_rate_override
    if override is not None:
        return _as_decimal(override)
    return DEFAULT_COMMISSION_RATE


def _first_of_month(now: datetime.datetime | None = None) -> datetime.date:
    """Return the first calendar day of the current (UTC) month."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return datetime.date(now.year, now.month, 1)


async def _get_or_create_wallet(
    session: AsyncSession, org_id: uuid.UUID
) -> PartnerWallet:
    """Fetch the org's Partner_Wallet, creating it (balance 0) if absent.

    There is exactly one wallet per org (``partner_wallets.org_id`` UNIQUE), so
    the first commission for a partner lazily creates the wallet.
    """
    result = await session.execute(
        select(PartnerWallet).where(PartnerWallet.org_id == org_id)
    )
    wallet = result.scalar_one_or_none()
    if wallet is None:
        wallet = PartnerWallet(org_id=org_id, balance=Decimal("0"))
        session.add(wallet)
        await session.flush()  # assign wallet.id
    return wallet


async def credit_commission(
    session: AsyncSession,
    *,
    org_id: Any,
    device_id: Any | None = None,
    payment_id: Any | None = None,
    period_month: datetime.date | None = None,
) -> Commission:
    """Credit a partner's wallet for one paid device-month (Req 18.1-18.3, 26.1).

    Resolves the commission rate for ``org_id`` (per-partner override or the ₹50
    default, including a zero override), then in a single transaction inserts a
    non-negative ``commissions`` row and increments the org's
    ``partner_wallets.balance`` by the same amount.

    Args:
        session: the active async DB session (the caller owns its lifecycle but
            this function commits the credit so insert+increment land together).
        org_id: the Project_Center organization being credited.
        device_id: the billed device (optional; recorded on the commission row).
        payment_id: the originating payment (optional; recorded for traceability).
        period_month: the paid month being credited; defaults to the first of
            the current UTC month.

    Returns:
        The persisted :class:`Commission` row.

    Raises:
        NotFoundError: if ``org_id`` does not resolve to an organization.
    """
    org_uuid = _to_uuid(org_id)
    org = await session.get(Organization, org_uuid)
    if org is None:
        raise NotFoundError("Organization not found for commission credit")

    rate = resolve_commission_rate(org)
    # Non-negativity invariant: a paid device-month credits one rate unit, never
    # less than zero even if a negative override somehow slipped through
    # (Req 18.1, commissions.amount >= 0).
    amount = rate if rate > 0 else Decimal("0")

    wallet = await _get_or_create_wallet(session, org_uuid)

    commission = Commission(
        org_id=org_uuid,
        wallet_id=wallet.id,
        device_id=_to_uuid(device_id) if device_id is not None else None,
        payment_id=_to_uuid(payment_id) if payment_id is not None else None,
        amount=amount,
        period_month=period_month or _first_of_month(),
    )
    session.add(commission)

    # Increment the wallet balance by exactly the credited amount so the wallet
    # stays in lockstep with its commissions (Req 18.3). amount >= 0 and the
    # prior balance >= 0, so the balance >= 0 invariant is preserved.
    wallet.balance = _as_decimal(wallet.balance) + amount

    await session.commit()
    await session.refresh(commission)
    return commission
