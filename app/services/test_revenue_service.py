"""Unit tests for revenue analytics computation (Task 20.3, Req 25.1, 25.2).

Drives :mod:`app.services.revenue_service` against an in-memory SQLite DB with a
handful of organizations/subscriptions/payments and asserts each metric
(MRR, ARR, churn, funnel, ARPU, by_source, top_orgs) is computed from the
current billing state. Also asserts the metrics move when new billing data is
recorded (Req 25.2).
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
from app.models.billing import Payment, Subscription
from app.models.organization import Organization
from app.services import revenue_service

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    Subscription.__table__,
    Payment.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture()
def engine():
    _prepare_tables()
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
async def session_factory(engine):
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Two orgs: one monthly-active payer, one yearly-active payer; one cancelled."""
    org_a = Organization(name="Alpha", type="project_center", plan="pro")
    org_b = Organization(name="Beta", type="project_center", plan="pro")
    org_c = Organization(name="Gamma", type="project_center", plan="free")
    session.add_all([org_a, org_b, org_c])
    await session.flush()

    # Alpha: 5 devices @ 99 monthly active -> MRR 495.
    sub_a = Subscription(
        org_id=org_a.id, plan="pro", billing_cycle="monthly",
        device_count=5, unit_price=99, status="active",
    )
    # Beta: 12 devices @ 948 yearly active -> monthly 12*948/12 = 948.
    sub_b = Subscription(
        org_id=org_b.id, plan="pro", billing_cycle="yearly",
        device_count=12, unit_price=948, status="active",
    )
    # Gamma: cancelled subscription (counts toward churn).
    sub_c = Subscription(
        org_id=org_c.id, plan="pro", billing_cycle="monthly",
        device_count=2, unit_price=99, status="cancelled",
    )
    session.add_all([sub_a, sub_b, sub_c])
    await session.flush()

    # Captured payments: Alpha 495, Beta 11376; a failed one is ignored.
    session.add_all([
        Payment(org_id=org_a.id, subscription_id=sub_a.id, amount=Decimal("495"),
                status="captured"),
        Payment(org_id=org_b.id, subscription_id=sub_b.id, amount=Decimal("11376"),
                status="captured"),
        Payment(org_id=org_a.id, subscription_id=sub_a.id, amount=Decimal("100"),
                status="failed"),
    ])
    await session.commit()
    return {"org_a": org_a.id, "org_b": org_b.id, "org_c": org_c.id}


@pytest.mark.asyncio
async def test_mrr_arr_and_arpu(session_factory):
    async with session_factory() as s:
        await _seed(s)
        result = await revenue_service.compute_revenue_analytics(s)

    # MRR = 495 (Alpha monthly) + 948 (Beta yearly normalised) = 1443.
    assert result["mrr"] == pytest.approx(1443.0)
    assert result["arr"] == pytest.approx(1443.0 * 12)
    # ARPU = MRR / 2 paying orgs.
    assert result["arpu"] == pytest.approx(1443.0 / 2)


@pytest.mark.asyncio
async def test_churn_and_funnel(session_factory):
    async with session_factory() as s:
        await _seed(s)
        result = await revenue_service.compute_revenue_analytics(s)

    # 1 of 3 subscriptions cancelled.
    assert result["churn"] == pytest.approx(1 / 3, abs=1e-4)
    funnel = result["funnel"]
    assert funnel["organizations"] == 3
    assert funnel["with_subscription"] == 3
    assert funnel["paying"] == 2
    assert funnel["conversion_rate"] == pytest.approx(2 / 3, abs=1e-4)


@pytest.mark.asyncio
async def test_by_source_and_top_orgs(session_factory):
    async with session_factory() as s:
        ids = await _seed(s)
        result = await revenue_service.compute_revenue_analytics(s)

    # Captured revenue grouped by cycle (failed payment excluded).
    assert result["by_source"]["monthly"] == pytest.approx(495.0)
    assert result["by_source"]["yearly"] == pytest.approx(11376.0)

    top = result["top_orgs"]
    assert top[0]["org_id"] == str(ids["org_b"])
    assert top[0]["revenue"] == pytest.approx(11376.0)
    assert top[1]["org_id"] == str(ids["org_a"])
    assert top[1]["revenue"] == pytest.approx(495.0)


@pytest.mark.asyncio
async def test_metrics_update_on_new_billing_data(session_factory):
    """New active subscription data changes the metrics (Req 25.2)."""
    async with session_factory() as s:
        ids = await _seed(s)
        before = await revenue_service.compute_revenue_analytics(s)

        # Record a new active subscription for Gamma -> MRR rises, churn drops.
        s.add(Subscription(
            org_id=ids["org_c"], plan="pro", billing_cycle="monthly",
            device_count=10, unit_price=99, status="active",
        ))
        await s.commit()
        after = await revenue_service.compute_revenue_analytics(s)

    assert after["mrr"] == pytest.approx(before["mrr"] + 990.0)
    assert after["funnel"]["paying"] == before["funnel"]["paying"] + 1
    # Churn share falls as the denominator grows with the new subscription.
    assert after["churn"] < before["churn"]


@pytest.mark.asyncio
async def test_empty_platform_returns_zeroes(session_factory):
    async with session_factory() as s:
        result = await revenue_service.compute_revenue_analytics(s)
    assert result["mrr"] == 0.0
    assert result["arr"] == 0.0
    assert result["arpu"] == 0.0
    assert result["churn"] == 0.0
    assert result["funnel"]["conversion_rate"] == 0.0
    assert result["by_source"] == {}
    assert result["top_orgs"] == []
