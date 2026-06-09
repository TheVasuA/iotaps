"""Unit tests for the subscription service core logic (Task 15.1, Req 17).

Covers the pure helpers (coupon math, period advance) and the webhook state
machine against an in-memory SQLite DB, asserting on persisted billing state:

    - payment.captured activates the subscription and stamps a period (17.2)
    - a renewal capture extends the period from the current end (auto-debit, 17.6)
    - payment.failed marks the payment failed but RETAINS the subscription's
      prior status/period and records a notification (17.3)
    - duplicate capture events are idempotent
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.security.principal import Principal, ROLE_PROJECT_CENTER
from app.core.security.tenant import TenantScope
from app.db.base import Base
from app.models.billing import Coupon, Payment, Subscription
from app.models.device import Device
from app.models.infra import MqttNode
from app.models.ops import ActivityLog, Notification
from app.models.organization import Organization
from app.models.user import User
from app.services import subscription_service as svc
from app.services.razorpay_client import RazorpayClient

import app.models  # noqa: F401

_TABLES = [
    Organization.__table__,
    User.__table__,
    MqttNode.__table__,
    Device.__table__,
    Coupon.__table__,
    Subscription.__table__,
    Payment.__table__,
    Notification.__table__,
    ActivityLog.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    ActivityLog.__table__.c.detail.type = JSON()


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


@pytest.fixture()
async def ctx(session_factory):
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        s.add(org)
        await s.flush()
        user = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        s.add(user)
        await s.commit()
        return {"factory": session_factory, "org_id": str(org.id), "user_id": str(user.id)}


def _scope(session: AsyncSession, org_id: str, user_id: str) -> TenantScope:
    principal = Principal(user_id=user_id, org_id=org_id, role=ROLE_PROJECT_CENTER)
    return TenantScope(principal, session)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_apply_percent_coupon():
    coupon = Coupon(code="P10", discount_type="percent", value=10, active=True)
    assert svc.apply_coupon_discount(1000, coupon) == 900


def test_apply_fixed_coupon_never_below_zero():
    coupon = Coupon(code="BIG", discount_type="fixed", value=5000, active=True)
    assert svc.apply_coupon_discount(1000, coupon) == 0


def test_apply_no_coupon():
    assert svc.apply_coupon_discount(1234, None) == 1234


def test_add_period_monthly_rolls_year():
    start = datetime(2025, 12, 15, tzinfo=timezone.utc)
    end = svc._add_period(start, "monthly")
    assert (end.year, end.month, end.day) == (2026, 1, 15)


def test_add_period_yearly():
    start = datetime(2025, 3, 1, tzinfo=timezone.utc)
    end = svc._add_period(start, "yearly")
    assert (end.year, end.month, end.day) == (2026, 3, 1)


# ---------------------------------------------------------------------------
# subscribe + webhook
# ---------------------------------------------------------------------------
async def _make_subscription(ctx) -> dict:
    async with ctx["factory"]() as s:
        scope = _scope(s, ctx["org_id"], ctx["user_id"])
        service = svc.SubscriptionService(scope, RazorpayClient())
        return await service.subscribe(device_count=3, billing_cycle="monthly")


@pytest.mark.asyncio
async def test_subscribe_persists_pending_state(ctx):
    result = await _make_subscription(ctx)
    assert result["amount_due"] == 3 * 99
    async with ctx["factory"]() as s:
        sub = (await s.execute(select(Subscription))).scalar_one()
        pay = (await s.execute(select(Payment))).scalar_one()
        assert sub.status == svc.SUB_STATUS_CREATED
        assert sub.current_period_end is None
        assert pay.status == svc.PAY_STATUS_CREATED
        assert pay.razorpay_order_id == result["razorpay_order"]["id"]


@pytest.mark.asyncio
async def test_capture_activates_and_sets_period(ctx):
    result = await _make_subscription(ctx)
    order_id = result["razorpay_order"]["id"]
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_a", "order_id": order_id}}},
    }
    async with ctx["factory"]() as s:
        status = await svc.process_webhook_event(s, event)
        assert status == "captured"
    async with ctx["factory"]() as s:
        sub = (await s.execute(select(Subscription))).scalar_one()
        pay = (await s.execute(select(Payment))).scalar_one()
        assert sub.status == svc.SUB_STATUS_ACTIVE
        assert sub.current_period_start is not None
        assert sub.current_period_end is not None
        assert sub.current_period_end > sub.current_period_start
        assert pay.status == svc.PAY_STATUS_CAPTURED
        assert pay.razorpay_payment_id == "pay_a"
        assert pay.paid_at is not None


@pytest.mark.asyncio
async def test_renewal_capture_extends_period(ctx):
    result = await _make_subscription(ctx)
    order_id = result["razorpay_order"]["id"]
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_a", "order_id": order_id}}},
    }
    async with ctx["factory"]() as s:
        await svc.process_webhook_event(s, event)
    async with ctx["factory"]() as s:
        first_end = (await s.execute(select(Subscription))).scalar_one().current_period_end

    # Simulate an auto-debit renewal: a new payment for the same subscription.
    async with ctx["factory"]() as s:
        sub = (await s.execute(select(Subscription))).scalar_one()
        renewal = Payment(
            org_id=uuid.UUID(ctx["org_id"]),
            subscription_id=sub.id,
            amount=3 * 99,
            currency="INR",
            status=svc.PAY_STATUS_CREATED,
            razorpay_order_id="order_renewal",
        )
        s.add(renewal)
        await s.commit()
    renewal_event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_b", "order_id": "order_renewal"}}},
    }
    async with ctx["factory"]() as s:
        await svc.process_webhook_event(s, renewal_event)
    async with ctx["factory"]() as s:
        second_end = (await s.execute(select(Subscription))).scalar_one().current_period_end

    # Renewal stacks: the new end is later than the first period end (Req 17.6).
    assert second_end > first_end


@pytest.mark.asyncio
async def test_failure_retains_state_and_notifies(ctx):
    result = await _make_subscription(ctx)
    order_id = result["razorpay_order"]["id"]
    event = {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": "pay_f", "order_id": order_id}}},
    }
    async with ctx["factory"]() as s:
        status = await svc.process_webhook_event(s, event)
        assert status == "failed"
    async with ctx["factory"]() as s:
        sub = (await s.execute(select(Subscription))).scalar_one()
        pay = (await s.execute(select(Payment))).scalar_one()
        notes = (await s.execute(select(Notification))).scalars().all()
        # Prior state retained: still 'created', no period granted (Req 17.3).
        assert sub.status == svc.SUB_STATUS_CREATED
        assert sub.current_period_end is None
        assert pay.status == svc.PAY_STATUS_FAILED
        # Customer was notified.
        assert len(notes) == 1
        assert notes[0].channel == "in_app"


@pytest.mark.asyncio
async def test_duplicate_capture_is_idempotent(ctx):
    result = await _make_subscription(ctx)
    order_id = result["razorpay_order"]["id"]
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_a", "order_id": order_id}}},
    }
    async with ctx["factory"]() as s:
        await svc.process_webhook_event(s, event)
    async with ctx["factory"]() as s:
        end_after_first = (await s.execute(select(Subscription))).scalar_one().current_period_end
    async with ctx["factory"]() as s:
        await svc.process_webhook_event(s, event)
    async with ctx["factory"]() as s:
        end_after_second = (await s.execute(select(Subscription))).scalar_one().current_period_end
    assert end_after_first == end_after_second
