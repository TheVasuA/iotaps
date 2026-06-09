"""Unit tests for partner payout request & approval (Task 16.3, Req 18.4-18.6, 26.3).

Uses an in-memory SQLite async session (no live Postgres/RazorpayX). Only the
tables the payout path touches are created (``organizations``,
``partner_wallets``, ``commissions``, ``payouts``), and their Postgres-specific
``gen_random_uuid()`` PK defaults are swapped for Python uuid4 so SQLite can
evaluate them. RazorpayX transfers go through the offline default client.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import NotFoundError, ValidationError
from app.db.base import Base
from app.models.billing import Commission, PartnerWallet, Payout
from app.models.organization import Organization
from app.services import payout_service as ps

_TEST_TABLES = [
    Organization.__table__,
    PartnerWallet.__table__,
    Commission.__table__,
    Payout.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture
async def session() -> AsyncSession:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_org_with_wallet(
    session: AsyncSession, *, balance: Decimal
) -> tuple[Organization, PartnerWallet]:
    org = Organization(name="Acme", plan="pro")
    session.add(org)
    await session.flush()
    wallet = PartnerWallet(org_id=org.id, balance=balance)
    session.add(wallet)
    await session.commit()
    return org, wallet


# ---------------------------------------------------------------------------
# request_payout (Req 18.4, 18.6)
# ---------------------------------------------------------------------------
async def test_request_payout_within_balance_creates_pending(session):
    org, _ = await _add_org_with_wallet(session, balance=Decimal("100"))

    payout = await ps.request_payout(
        session, org_id=org.id, amount=Decimal("40"), destination="upi:acme@bank"
    )

    assert payout.status == ps.PAYOUT_PENDING
    assert Decimal(str(payout.amount)) == Decimal("40")
    assert payout.destination == "upi:acme@bank"
    assert payout.requested_at is not None


async def test_request_payout_equal_to_balance_is_allowed(session):
    org, _ = await _add_org_with_wallet(session, balance=Decimal("100"))

    payout = await ps.request_payout(session, org_id=org.id, amount=Decimal("100"))

    assert payout.status == ps.PAYOUT_PENDING


async def test_request_payout_exceeding_balance_is_rejected(session):
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("100"))

    with pytest.raises(ValidationError) as exc:
        await ps.request_payout(session, org_id=org.id, amount=Decimal("100.01"))
    assert exc.value.error_code == "insufficient_balance"

    # Wallet untouched on rejection (Req 18.6).
    await session.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal("100")


async def test_request_payout_rejects_non_positive_amount(session):
    org, _ = await _add_org_with_wallet(session, balance=Decimal("100"))

    with pytest.raises(ValidationError):
        await ps.request_payout(session, org_id=org.id, amount=Decimal("0"))


async def test_request_payout_without_wallet_raises_not_found(session):
    org = Organization(name="NoWallet", plan="pro")
    session.add(org)
    await session.commit()

    with pytest.raises(NotFoundError):
        await ps.request_payout(session, org_id=org.id, amount=Decimal("10"))


# ---------------------------------------------------------------------------
# approve_payout (Req 18.5, 26.3)
# ---------------------------------------------------------------------------
async def test_approve_payout_debits_wallet_and_sets_paid(session):
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("100"))
    payout = await ps.request_payout(session, org_id=org.id, amount=Decimal("60"))
    approver = uuid.uuid4()

    approved = await ps.approve_payout(
        session, payout_id=payout.id, approved_by=approver
    )

    assert approved.status == ps.PAYOUT_PAID
    assert approved.razorpayx_payout_id is not None
    assert approved.razorpayx_payout_id.startswith("pout_")
    assert approved.approved_by == approver
    assert approved.approved_at is not None

    await session.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal("40")
    assert Decimal(str(wallet.balance)) >= 0


async def test_approve_full_balance_leaves_zero_balance(session):
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("100"))
    payout = await ps.request_payout(session, org_id=org.id, amount=Decimal("100"))

    await ps.approve_payout(session, payout_id=payout.id)

    await session.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal("0")


async def test_approve_rechecks_balance_at_approval(session):
    # Two payouts requested while balance covers both individually, but a prior
    # approval drains the wallet so the second can no longer be paid.
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("100"))
    p1 = await ps.request_payout(session, org_id=org.id, amount=Decimal("80"))
    p2 = await ps.request_payout(session, org_id=org.id, amount=Decimal("80"))

    await ps.approve_payout(session, payout_id=p1.id)

    with pytest.raises(ValidationError) as exc:
        await ps.approve_payout(session, payout_id=p2.id)
    assert exc.value.error_code == "insufficient_balance"

    await session.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal("20")


async def test_approve_non_pending_payout_is_rejected(session):
    org, _ = await _add_org_with_wallet(session, balance=Decimal("100"))
    payout = await ps.request_payout(session, org_id=org.id, amount=Decimal("10"))
    await ps.approve_payout(session, payout_id=payout.id)

    # Re-approving an already PAID payout is rejected.
    with pytest.raises(ValidationError) as exc:
        await ps.approve_payout(session, payout_id=payout.id)
    assert exc.value.error_code == "payout_not_pending"


async def test_approve_unknown_payout_raises_not_found(session):
    with pytest.raises(NotFoundError):
        await ps.approve_payout(session, payout_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# get_wallet_summary (Req 18.4)
# ---------------------------------------------------------------------------
async def test_wallet_summary_returns_balance_and_commissions(session):
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("50"))
    session.add(
        Commission(org_id=org.id, wallet_id=wallet.id, amount=Decimal("50"))
    )
    await session.commit()

    summary = await ps.get_wallet_summary(session, org.id)

    assert Decimal(str(summary["balance"])) == Decimal("50")
    assert len(summary["commissions"]) == 1
    assert Decimal(str(summary["commissions"][0]["amount"])) == Decimal("50")


async def test_wallet_summary_without_wallet_is_zero(session):
    org = Organization(name="NoWallet", plan="pro")
    session.add(org)
    await session.commit()

    summary = await ps.get_wallet_summary(session, org.id)

    assert summary["balance"] == 0
    assert summary["commissions"] == []
