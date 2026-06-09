"""Endpoint + service tests for the refund window enforcement (Task 15.2).

Exercises POST /billing/refund end to end against an in-memory SQLite DB (via a
dependency override). No live Razorpay call is made: refund creation is offline
(``RazorpayClient`` mints a local refund id). Covers (Req 17.5, 17.7):

    - a refund requested within 14 days of purchase is accepted + processed
    - a refund requested exactly at the 14-day boundary is accepted
    - a refund requested after the 14-day window is rejected
    - only a captured payment can be refunded; a double refund is rejected
    - a payment in another org cannot be refunded (tenant isolation)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.api.v1 import billing as billing_module
from app.core import config as config_module
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.billing import Coupon, Payment, Subscription
from app.models.device import Device
from app.models.infra import MqttNode
from app.models.ops import ActivityLog, Notification
from app.models.organization import Organization
from app.models.user import User
from app.services.subscription_service import (
    PAY_STATUS_CAPTURED,
    PAY_STATUS_CREATED,
    PAY_STATUS_REFUNDED,
)

import app.models  # noqa: F401  (register all models on Base.metadata)

_WEBHOOK_SECRET = "test-webhook-secret"

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


def _settings() -> Settings:
    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        razorpay_webhook_secret=_WEBHOOK_SECRET,
    )


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


async def _make_payment(
    session_factory,
    *,
    org_id: uuid.UUID,
    status: str = PAY_STATUS_CAPTURED,
    paid_at: datetime | None,
    razorpay_payment_id: str | None = "pay_123",
    amount: int = 495,
) -> uuid.UUID:
    async with session_factory() as s:
        sub = Subscription(org_id=org_id, plan="pro", billing_cycle="monthly",
                           device_count=5, status="active")
        s.add(sub)
        await s.flush()
        payment = Payment(
            org_id=org_id,
            subscription_id=sub.id,
            amount=amount,
            currency="INR",
            status=status,
            razorpay_order_id="order_abc",
            razorpay_payment_id=razorpay_payment_id,
            paid_at=paid_at,
        )
        s.add(payment)
        await s.commit()
        return payment.id


@pytest.fixture()
async def seeded(session_factory):
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="pro")
        other = Organization(name="Other", type="project_center", plan="pro")
        s.add_all([org, other])
        await s.flush()
        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        s.add(pc)
        await s.commit()
        return {
            "org_id": org.id,
            "other_org_id": other.id,
            "pc_id": str(pc.id),
        }


@pytest.fixture()
def client(session_factory, monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    monkeypatch.setattr(config_module, "get_settings", _settings, raising=False)
    monkeypatch.setattr(billing_module, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth(user_id: str, org_id: str, role: str = ROLE_PROJECT_CENTER) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=_settings()
    )
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# refund window
# ---------------------------------------------------------------------------
def test_refund_requires_auth(client):
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 401


async def test_refund_within_window_is_processed(client, seeded, session_factory):
    payment_id = await _make_payment(
        session_factory, org_id=seeded["org_id"], paid_at=_now() - timedelta(days=3)
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == PAY_STATUS_REFUNDED
    assert body["refunded_at"] is not None
    assert body["razorpay_refund"]["id"].startswith("rfnd_")
    assert body["razorpay_refund"]["payment_id"] == "pay_123"
    # ₹495 -> 49500 paise.
    assert body["razorpay_refund"]["amount"] == 495 * 100


async def test_refund_at_boundary_is_accepted(client, seeded, session_factory):
    # Just inside 14 days.
    payment_id = await _make_payment(
        session_factory,
        org_id=seeded["org_id"],
        paid_at=_now() - timedelta(days=14) + timedelta(minutes=1),
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == PAY_STATUS_REFUNDED


async def test_refund_after_window_is_rejected(client, seeded, session_factory):
    payment_id = await _make_payment(
        session_factory, org_id=seeded["org_id"], paid_at=_now() - timedelta(days=15)
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error_code"] == "refund_window_elapsed"


async def test_refund_rejects_uncaptured_payment(client, seeded, session_factory):
    payment_id = await _make_payment(
        session_factory,
        org_id=seeded["org_id"],
        status=PAY_STATUS_CREATED,
        paid_at=_now(),
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error_code"] == "payment_not_refundable"


async def test_refund_rejects_double_refund(client, seeded, session_factory):
    payment_id = await _make_payment(
        session_factory,
        org_id=seeded["org_id"],
        status=PAY_STATUS_REFUNDED,
        paid_at=_now(),
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error_code"] == "already_refunded"


async def test_refund_denies_cross_org_payment(client, seeded, session_factory):
    # Payment belongs to another org; the caller must not be able to refund it.
    payment_id = await _make_payment(
        session_factory,
        org_id=seeded["other_org_id"],
        paid_at=_now() - timedelta(days=1),
    )
    headers = _auth(seeded["pc_id"], str(seeded["org_id"]))
    resp = client.post(
        _url("/billing/refund"), json={"payment_id": str(payment_id)}, headers=headers
    )
    assert resp.status_code == 403, resp.text
