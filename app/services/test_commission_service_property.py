"""Property-based test for commission crediting (Task 16.2, Req 18.1-18.3, 26.1).

# Feature: iotaps-platform, Property 12: Commission is non-negative and matches the resolved rate

Property 12 (design.md "Correctness Properties"):

    For any paid device-month with any default or per-partner override rate
    (including a configured rate of zero), the credited commission is greater
    than or equal to zero, equals the resolved rate amount, and increases the
    Partner_Wallet balance by exactly that amount.

Validates: Requirements 18.1, 18.2, 18.3, 26.1

Drives the real :func:`app.services.commission_service.credit_commission`
against an in-memory SQLite database (no live Postgres/Razorpay). Each
Hypothesis example generates an organization that either uses the ₹50 default
(``commission_rate_override is None``) or a per-partner override (including a
configured zero), plus a number of paid device-months to credit. After each
credit we assert the commission row is non-negative and equals the resolved
rate, and after all credits we assert the wallet balance equals the sum of all
credited commissions.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.db.base import Base
from app.models.billing import Commission, PartnerWallet
from app.models.organization import Organization
from app.services import commission_service as cs

# Only the tables the credit path touches (the full metadata pulls in
# Postgres-only DDL from unrelated models).
_TABLES = [
    Organization.__table__,
    PartnerWallet.__table__,
    Commission.__table__,
]


def _prepare_tables() -> None:
    """Swap each table's ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


def _make_engine():
    _prepare_tables()
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


# ---------------------------------------------------------------------------
# Generators: an optional override rate (None -> default ₹50, including zero)
# and a count of paid device-months to credit.
# ---------------------------------------------------------------------------
# Override values are non-negative Decimals (a configured rate is never
# negative); ``None`` exercises the ₹50 default fallback. Zero is included as a
# valid "no commission" setting (Req 26.1).
_override = st.one_of(
    st.none(),
    st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("10000"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
)
_credit_count = st.integers(min_value=1, max_value=12)


async def _wallet_balance(session: AsyncSession, org_id: uuid.UUID) -> Decimal:
    result = await session.execute(
        select(PartnerWallet).where(PartnerWallet.org_id == org_id)
    )
    wallet = result.scalar_one_or_none()
    return Decimal(str(wallet.balance)) if wallet is not None else Decimal("0")


async def _run(override: Decimal | None, count: int) -> None:
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with factory() as session:
            org = Organization(
                name="Org", plan="pro", commission_rate_override=override
            )
            session.add(org)
            await session.flush()
            org_id = org.id
            await session.commit()

            # The resolved rate the credit path must use (default ₹50 or the
            # override, including a configured zero) (Req 18.1, 18.2, 26.1).
            expected_rate = cs.resolve_commission_rate(org)
            expected_amount = expected_rate if expected_rate > 0 else Decimal("0")

            running_total = Decimal("0")
            for _ in range(count):
                commission = await cs.credit_commission(
                    session,
                    org_id=org_id,
                    device_id=uuid.uuid4(),
                    payment_id=uuid.uuid4(),
                )
                amount = Decimal(str(commission.amount))

                # Non-negativity invariant (Req 18.1, commissions.amount >= 0).
                assert amount >= 0, f"commission {amount} is negative"
                # The credited amount equals the resolved rate (Req 18.1, 18.2,
                # 26.1).
                assert amount == expected_amount, (
                    f"credited {amount} != resolved rate {expected_amount} "
                    f"(override={override!r})"
                )

                running_total += amount

                # The wallet balance increased by exactly the credited amount
                # and stays in lockstep with the running total (Req 18.3).
                balance = await _wallet_balance(session, org_id)
                assert balance == running_total, (
                    f"wallet balance {balance} != cumulative credits "
                    f"{running_total}"
                )
                assert balance >= 0, "wallet balance went negative"

            # Final invariant straight from the DB: wallet balance equals the
            # sum of all its commission rows (Req 18.3).
            commissions = (
                await session.execute(
                    select(Commission).where(Commission.org_id == org_id)
                )
            ).scalars().all()
            assert len(commissions) == count
            commissions_sum = sum(
                (Decimal(str(c.amount)) for c in commissions), Decimal("0")
            )
            final_balance = await _wallet_balance(session, org_id)
            assert final_balance == commissions_sum, (
                f"final wallet balance {final_balance} != sum of commissions "
                f"{commissions_sum}"
            )
    finally:
        await engine.dispose()


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(override=_override, count=_credit_count)
def test_commission_non_negative_and_matches_rate(
    override: Decimal | None, count: int
) -> None:
    """Property 12: Commission is non-negative and matches the resolved rate.

    Validates: Requirements 18.1, 18.2, 18.3, 26.1
    """
    asyncio.run(_run(override, count))
