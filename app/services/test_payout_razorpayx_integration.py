"""Integration test for the RazorpayX partner payout transfer (Task 16.5, Req 18.5).

Verifies the *external transfer* half of payout approval: approving a PENDING
payout must (a) invoke the RazorpayX transfer with the correct amount (in paise)
and destination, and (b) transition the payout to ``PAID`` with the RazorpayX
payout id recorded (Req 18.5).

Runs against an in-memory SQLite async session (no live Postgres) following the
same table-prep convention as ``test_payout_service.py``. The RazorpayX client
is a spy that records the call and returns a deterministic payout id - no live
RazorpayX API call and no real secret is used.
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

from app.db.base import Base
from app.models.billing import Commission, PartnerWallet, Payout
from app.models.organization import Organization
from app.services import payout_service as ps
from app.services.razorpay_client import PAISE_PER_RUPEE, RazorpayXPayout

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


class SpyRazorpayXClient:
    """A spy RazorpayX client recording transfer calls (no live API).

    Mirrors :meth:`RazorpayXClient.transfer` (keyword-only ``amount`` in paise,
    ``destination``, ``currency``) so it is a drop-in for the injected client,
    and records every call so the test can assert the transfer arguments.
    """

    def __init__(self, payout_id: str = "pout_spy_0001") -> None:
        self.payout_id = payout_id
        self.calls: list[dict] = []

    def transfer(
        self,
        *,
        amount: int,
        destination,
        currency: str = "INR",
    ) -> RazorpayXPayout:
        self.calls.append(
            {"amount": amount, "destination": destination, "currency": currency}
        )
        return RazorpayXPayout(
            id=self.payout_id,
            amount=amount,
            currency=currency,
            destination=destination,
            status="processed",
        )


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


async def test_approve_payout_calls_razorpayx_transfer_and_transitions_to_paid(session):
    """Approving a payout transfers via RazorpayX and records PAID (Req 18.5).

    Asserts the transfer is invoked exactly once with the payout amount in paise
    and the requested destination, and that the payout transitions to ``PAID``
    with the RazorpayX-returned payout id persisted.
    """
    org, wallet = await _add_org_with_wallet(session, balance=Decimal("100"))
    payout = await ps.request_payout(
        session, org_id=org.id, amount=Decimal("60"), destination="upi:acme@bank"
    )
    spy = SpyRazorpayXClient(payout_id="pout_integration_xyz")

    approved = await ps.approve_payout(
        session, payout_id=payout.id, approved_by=uuid.uuid4(), razorpayx=spy
    )

    # RazorpayX transfer invoked once with the right amount (paise) + destination.
    assert len(spy.calls) == 1
    assert spy.calls[0]["amount"] == 60 * PAISE_PER_RUPEE
    assert spy.calls[0]["destination"] == "upi:acme@bank"
    assert spy.calls[0]["currency"] == "INR"

    # Status transitions to PAID with the RazorpayX payout id recorded (Req 18.5).
    assert approved.status == ps.PAYOUT_PAID
    assert approved.razorpayx_payout_id == "pout_integration_xyz"

    # The transition is durable (re-read from the DB).
    persisted = await session.get(Payout, payout.id)
    assert persisted.status == ps.PAYOUT_PAID
    assert persisted.razorpayx_payout_id == "pout_integration_xyz"

    # Wallet debited by exactly the payout amount, staying >= 0.
    await session.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal("40")
    assert Decimal(str(wallet.balance)) >= 0


async def test_rejected_approval_does_not_call_razorpayx_transfer(session):
    """A re-checked over-balance approval must not transfer via RazorpayX (Req 18.5).

    When a prior approval drains the wallet, the second approval is rejected at
    the balance re-check *before* any external transfer, so the spy is never
    invoked for the rejected payout and its status stays PENDING.
    """
    org, _ = await _add_org_with_wallet(session, balance=Decimal("100"))
    p1 = await ps.request_payout(session, org_id=org.id, amount=Decimal("80"))
    p2 = await ps.request_payout(session, org_id=org.id, amount=Decimal("80"))
    spy = SpyRazorpayXClient()

    await ps.approve_payout(session, payout_id=p1.id, razorpayx=spy)
    assert len(spy.calls) == 1  # only the first payout was transferred

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        await ps.approve_payout(session, payout_id=p2.id, razorpayx=spy)

    # No additional transfer happened for the rejected payout.
    assert len(spy.calls) == 1
    persisted = await session.get(Payout, p2.id)
    assert persisted.status == ps.PAYOUT_PENDING
    assert persisted.razorpayx_payout_id is None
