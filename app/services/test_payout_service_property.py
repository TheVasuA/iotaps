"""Property test for partner payout never exceeding wallet balance (Task 16.4).

# Feature: iotaps-platform, Property 13: Payout never exceeds wallet balance

Property 13 (design.md "Payout (never exceeds balance)", Req 18.5, 18.6):
For any sequence of payout requests and approvals against a wallet, the wallet
balance never goes negative, and no approved payout ever debits more than the
balance available at approval time.

Uses an in-memory SQLite async session (no live Postgres/RazorpayX), mirroring
``app.services.test_payout_service``: only the tables the payout path touches
are created and their Postgres ``gen_random_uuid()`` PK defaults are swapped for
Python uuid4 so SQLite can evaluate them. RazorpayX transfers go through the
offline default client.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import ValidationError
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


async def _make_session_factory():
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
    return engine, factory


async def _add_org_with_wallet(
    session: AsyncSession, *, balance: Decimal
) -> Organization:
    org = Organization(name="Acme", plan="pro")
    session.add(org)
    await session.flush()
    wallet = PartnerWallet(org_id=org.id, balance=balance)
    session.add(wallet)
    await session.commit()
    return org


# Operations against a single wallet: each is a rupee amount to request then
# (when accepted) immediately attempt to approve. Mixing accepted/rejected
# requests and over-balance approvals exercises both guards (Req 18.5/18.6).
_amounts = st.lists(
    st.integers(min_value=1, max_value=500),
    min_size=1,
    max_size=12,
)


async def _run_scenario(initial_balance: int, amounts: list[int]) -> None:
    engine, factory = await _make_session_factory()
    try:
        async with factory() as session:
            org = await _add_org_with_wallet(
                session, balance=Decimal(initial_balance)
            )

            for amount in amounts:
                amt = Decimal(amount)
                # Request: rejected up front when it exceeds the balance (18.6).
                try:
                    payout = await ps.request_payout(
                        session, org_id=org.id, amount=amt
                    )
                except ValidationError:
                    payout = None

                if payout is not None:
                    # Approval re-checks the balance; capture it just before.
                    wallet = await ps._get_wallet_for_org(session, org.id)
                    balance_before = Decimal(str(wallet.balance))
                    try:
                        approved = await ps.approve_payout(
                            session, payout_id=payout.id
                        )
                    except ValidationError:
                        approved = None

                    if approved is not None:
                        # An approved payout never exceeds the balance it was
                        # debited against (Req 18.5).
                        assert amt <= balance_before

                # Invariant after every step: the wallet stays non-negative.
                wallet = await ps._get_wallet_for_org(session, org.id)
                assert Decimal(str(wallet.balance)) >= 0
    finally:
        await engine.dispose()


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(initial_balance=st.integers(min_value=0, max_value=1000), amounts=_amounts)
def test_payout_never_exceeds_wallet_balance(initial_balance, amounts):
    """Payout never exceeds wallet balance; balance never goes negative.

    **Validates: Requirements 18.5, 18.6**
    """
    asyncio.run(_run_scenario(initial_balance, amounts))
