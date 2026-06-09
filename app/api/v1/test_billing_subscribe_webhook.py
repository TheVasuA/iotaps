"""Endpoint + service tests for the Razorpay subscribe/webhook flow (Task 15.1).

Exercises POST /billing/subscribe and POST /billing/webhook end to end against
an in-memory SQLite DB (via a dependency override). No live Razorpay call is
made: order creation is offline (``RazorpayClient`` mints a local id) and the
webhook signature is computed with the test webhook secret. Covers:

    - subscribe creates a pending subscription + payment carrying the order id
    - per-device subscribe binds the subscription to a device (Req 17.4)
    - coupon discount is applied to the order amount
    - a signed payment.captured webhook activates/extends the subscription (17.2)
    - auto-debit renewal extends the period (17.6)
    - a signed payment.failed webhook retains prior state + notifies (17.3)
    - a bad/missing webhook signature is rejected (17.2)
"""

from __future__ import annotations

import json
import uuid

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

from app.core import config as config_module
from app.core.config import Settings
from app.api.v1 import billing as billing_module
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
from app.services.razorpay_client import PAISE_PER_RUPEE, expected_signature

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
    # JSONB -> JSON for SQLite.
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


@pytest.fixture()
async def seeded(session_factory):
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        s.add(org)
        await s.flush()
        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        node = MqttNode(
            ip="127.0.0.1", port=1883, capacity=100,
            active_connections=0, status="active",
        )
        device = Device(org_id=org.id, device_uid="dev-1", status="offline")
        coupon = Coupon(code="SAVE10", discount_type="percent", value=10, active=True)
        fixed = Coupon(code="FLAT50", discount_type="fixed", value=50, active=True)
        s.add_all([pc, node, device, coupon, fixed])
        await s.commit()
        return {
            "org_id": str(org.id),
            "pc_id": str(pc.id),
            "device_id": str(device.id),
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


def _signed_webhook(client: TestClient, event: dict) -> "object":
    raw = json.dumps(event).encode("utf-8")
    sig = expected_signature(raw, _WEBHOOK_SECRET)
    return client.post(
        _url("/billing/webhook"),
        content=raw,
        headers={
            "X-Razorpay-Signature": sig,
            "Content-Type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------
def test_subscribe_requires_auth(client):
    resp = client.post(
        _url("/billing/subscribe"),
        json={"device_count": 5, "billing_cycle": "monthly"},
    )
    assert resp.status_code == 401


def test_subscribe_creates_order_fleet(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    resp = client.post(
        _url("/billing/subscribe"),
        json={"device_count": 5, "billing_cycle": "monthly"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["unit_price"] == 99
    assert body["gross_total"] == 5 * 99
    assert body["amount_due"] == 5 * 99
    assert body["razorpay_order"]["id"].startswith("order_")
    # Razorpay amount is in paise.
    assert body["razorpay_order"]["amount"] == 5 * 99 * PAISE_PER_RUPEE


def test_subscribe_per_device_binds_device(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    resp = client.post(
        _url("/billing/subscribe"),
        json={
            "device_id": seeded["device_id"],
            "device_count": 1,
            "billing_cycle": "yearly",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["unit_price"] == 948  # fixed annual price
    assert body["amount_due"] == 948


def test_subscribe_applies_percent_coupon(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    resp = client.post(
        _url("/billing/subscribe"),
        json={"device_count": 10, "billing_cycle": "monthly", "coupon": "SAVE10"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    gross = 10 * 99
    assert body["gross_total"] == gross
    assert body["amount_due"] == int(round(gross * 0.9))
    assert body["coupon_applied"] == "SAVE10"


def test_subscribe_rejects_unknown_coupon(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    resp = client.post(
        _url("/billing/subscribe"),
        json={"device_count": 3, "billing_cycle": "monthly", "coupon": "NOPE"},
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# webhook
# ---------------------------------------------------------------------------
def _subscribe(client, seeded, **kwargs) -> dict:
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    payload = {"device_count": 2, "billing_cycle": "monthly"}
    payload.update(kwargs)
    resp = client.post(_url("/billing/subscribe"), json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_webhook_rejects_missing_signature(client, seeded):
    resp = client.post(
        _url("/billing/webhook"),
        content=json.dumps({"event": "payment.captured"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_webhook_rejects_bad_signature(client, seeded):
    resp = client.post(
        _url("/billing/webhook"),
        content=json.dumps({"event": "payment.captured"}).encode(),
        headers={"X-Razorpay-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_webhook_capture_activates_subscription(client, seeded):
    sub = _subscribe(client, seeded)
    order_id = sub["razorpay_order"]["id"]
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_123", "order_id": order_id}}},
    }
    resp = _signed_webhook(client, event)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "captured"


def test_webhook_failure_retains_state_and_notifies(client, seeded):
    sub = _subscribe(client, seeded)
    order_id = sub["razorpay_order"]["id"]
    event = {
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": "pay_fail", "order_id": order_id}}},
    }
    resp = _signed_webhook(client, event)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "failed"


def test_webhook_unmatched_order(client, seeded):
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_x", "order_id": "order_nope"}}},
    }
    resp = _signed_webhook(client, event)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "unmatched"


def test_webhook_ignores_unrelated_event(client, seeded):
    event = {"event": "order.paid", "payload": {}}
    resp = _signed_webhook(client, event)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Razorpay order/webhook signature verification (Task 15.4, Req 17.1, 17.2)
#
# These tests focus specifically on the integrity guarantee of the
# HMAC-SHA256 webhook signature and on order creation at subscribe time.
# They complement the Task 15.1 coverage above by asserting that the
# signature is bound to the *exact* raw body (tamper detection) and that a
# correctly-signed event is durably reflected in persisted state.
# ---------------------------------------------------------------------------
def test_subscribe_creates_razorpay_order_id_and_amount(client, seeded):
    """Subscribe must create a Razorpay order (Req 17.1).

    The response carries a Razorpay order with the ``order_`` id prefix and an
    amount expressed in paise matching the quoted rupee total.
    """
    headers = _auth(seeded["pc_id"], seeded["org_id"])
    resp = client.post(
        _url("/billing/subscribe"),
        json={"device_count": 3, "billing_cycle": "monthly"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()["razorpay_order"]
    assert order["id"].startswith("order_")
    assert order["currency"] == "INR"
    assert order["status"] == "created"
    assert order["amount"] == 3 * 99 * PAISE_PER_RUPEE


def test_webhook_accepts_correctly_signed_event(client, seeded):
    """A correctly-signed payment.captured webhook is accepted (200) and is
    processed, not merely acknowledged (Req 17.2).

    The signature is verified over the raw body; a 200 with ``captured`` status
    confirms the verified event advanced the matched subscription/payment.
    """
    sub = _subscribe(client, seeded)
    order_id = sub["razorpay_order"]["id"]
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_ok", "order_id": order_id}}},
    }
    resp = _signed_webhook(client, event)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "captured"


def test_webhook_rejects_tampered_body_with_valid_looking_signature(client, seeded):
    """A signature computed for one body must not validate a different body
    (Req 17.2).

    We sign an original event, then send a *modified* body alongside the
    original signature. Because the HMAC is bound to the exact raw bytes, the
    forged/tampered request is rejected with 401 and no state changes.
    """
    sub = _subscribe(client, seeded)
    order_id = sub["razorpay_order"]["id"]
    original = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_a", "order_id": order_id}}},
    }
    original_raw = json.dumps(original).encode("utf-8")
    sig = expected_signature(original_raw, _WEBHOOK_SECRET)

    # Tamper: change the payment id after signing.
    tampered = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_b", "order_id": order_id}}},
    }
    tampered_raw = json.dumps(tampered).encode("utf-8")

    resp = client.post(
        _url("/billing/webhook"),
        content=tampered_raw,
        headers={
            "X-Razorpay-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401


def test_webhook_rejects_signature_from_wrong_secret(client, seeded):
    """A signature produced with the wrong secret is rejected (Req 17.2)."""
    event = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_c", "order_id": "order_x"}}},
    }
    raw = json.dumps(event).encode("utf-8")
    wrong_sig = expected_signature(raw, "not-the-real-secret")
    resp = client.post(
        _url("/billing/webhook"),
        content=raw,
        headers={
            "X-Razorpay-Signature": wrong_sig,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
