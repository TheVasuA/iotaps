"""Unit tests for partner commission crediting (Task 16.1, Req 18.1-18.3, 26.1).

Uses an in-memory SQLite async session (no live Postgres/Razorpay). Only the
tables the credit path touches are created (``organizations``,
``partner_wallets``, ``commissions``), and their Postgres-specific
``gen_random_uuid()`` PK defaults are swapped for Python uuid4 so SQLite can
evaluate them.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import NotFoundError
from app.db.base import Base
from app.models.billing import Commission, PartnerWallet
from app.models.organization import Organization
from app.services import commission_service as cs

_TEST_TABLES = [
    Organization.__table__,
    PartnerWallet.__table__,
    Commission.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Swap each table's ``gen_random_uuid()`` PK default for a Python uuid4."""
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


async def _add_org(
    session: AsyncSession, *, override: Decimal | None = None
) -> Organization:
    org = Organization(name="Acme", plan="pro", commission_rate_override=override)
    session.add(org)
    await session.flush()
    return org


# ---------------------------------------------------------------------------
# resolve_commission_rate (Req 18.1, 18.2, 26.1)
# ---------------------------------------------------------------------------
def test_resolve_rate_defaults_to_50_when_no_override():
    org = Organization(name="A", plan="pro", commission_rate_override=None)
    assert cs.resolve_commission_rate(org) == Decimal("50")


def test_resolve_rate_uses_override_when_set():
    org = Organization(name="A", plan="pro", commission_rate_override=Decimal("75"))
    assert cs.resolve_commission_rate(org) == Decimal("75")


def test_resolve_rate_honours_zero_override():
    # A configured rate of zero is a valid "no commission" setting and must not
    # fall back to the ₹50 default (Req 18.2, 26.1).
    org = Organization(name="A", plan="pro", commission_rate_override=Decimal("0"))
    assert cs.resolve_commission_rate(org) == Decimal("0")


# ---------------------------------------------------------------------------
# credit_commission (Req 18.1-18.3)
# ---------------------------------------------------------------------------
async def test_credit_default_rate_creates_wallet_and_commission(session):
    org = await _add_org(session)

    commission = await cs.credit_commission(session, org_id=org.id)

    assert Decimal(str(commission.amount)) == Decimal("50")
    # The wallet was lazily created and credited by the same amount (Req 18.3).
    wallet = (
        await session.execute(
            select(PartnerWallet).where(PartnerWallet.org_id == org.id)
        )
    ).scalar_one()
    assert Decimal(str(wallet.balance)) == Decimal("50")
    assert commission.wallet_id == wallet.id


async def test_credit_uses_partner_override(session):
    org = await _add_org(session, override=Decimal("120"))

    commission = await cs.credit_commission(session, org_id=org.id)

    assert Decimal(str(commission.amount)) == Decimal("120")
    wallet = (
        await session.execute(
            select(PartnerWallet).where(PartnerWallet.org_id == org.id)
        )
    ).scalar_one()
    assert Decimal(str(wallet.balance)) == Decimal("120")


async def test_credit_zero_override_credits_nothing(session):
    org = await _add_org(session, override=Decimal("0"))

    commission = await cs.credit_commission(session, org_id=org.id)

    assert Decimal(str(commission.amount)) == Decimal("0")
    wallet = (
        await session.execute(
            select(PartnerWallet).where(PartnerWallet.org_id == org.id)
        )
    ).scalar_one()
    assert Decimal(str(wallet.balance)) == Decimal("0")


async def test_multiple_credits_accumulate_in_wallet(session):
    org = await _add_org(session)

    await cs.credit_commission(session, org_id=org.id)
    await cs.credit_commission(session, org_id=org.id)
    await cs.credit_commission(session, org_id=org.id)

    wallet = (
        await session.execute(
            select(PartnerWallet).where(PartnerWallet.org_id == org.id)
        )
    ).scalar_one()
    assert Decimal(str(wallet.balance)) == Decimal("150")

    # Wallet balance equals the sum of its commissions (Req 18.3 invariant).
    commissions = (
        await session.execute(
            select(Commission).where(Commission.org_id == org.id)
        )
    ).scalars().all()
    assert len(commissions) == 3
    assert sum(Decimal(str(c.amount)) for c in commissions) == Decimal(
        str(wallet.balance)
    )


async def test_credit_records_device_payment_and_period(session):
    org = await _add_org(session)
    device_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    period = datetime.date(2024, 3, 1)

    commission = await cs.credit_commission(
        session,
        org_id=org.id,
        device_id=device_id,
        payment_id=payment_id,
        period_month=period,
    )

    assert commission.device_id == device_id
    assert commission.payment_id == payment_id
    assert commission.period_month == period


async def test_credit_accepts_string_org_id(session):
    org = await _add_org(session)

    commission = await cs.credit_commission(session, org_id=str(org.id))

    assert Decimal(str(commission.amount)) == Decimal("50")


async def test_credit_unknown_org_raises_not_found(session):
    with pytest.raises(NotFoundError):
        await cs.credit_commission(session, org_id=uuid.uuid4())
