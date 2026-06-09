"""Endpoint tests for the admin coupons/commission/referral/content API (Task 20.4).

Exercises the Super_Admin surface from design.md ("Admin") for requirement
groups 26 and 27 end to end against an in-memory SQLite DB (dependency
override). Notification settings + site analytics run through the in-memory
platform-settings loader (no live Redis required).

Covered:
    - coupon CRUD + validation (Req 26)
    - per-partner commission override including zero, and clearing (Req 26.1, 26.2)
    - referral tracking with fraud flags (Req 26.4)
    - template CRUD (Req 27.2)
    - notification settings read/update (Req 27.3)
    - site analytics (Req 27.1)
    - Super_Admin-only access enforcement
"""

from __future__ import annotations

import uuid
from decimal import Decimal

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

import app.models  # noqa: F401  (register all model tables)
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.billing import Coupon
from app.models.infra import Template
from app.models.organization import Organization
from app.models.referral import Referral
from app.models.user import User

_TABLES = [
    Organization.__table__,
    User.__table__,
    Coupon.__table__,
    Template.__table__,
    Referral.__table__,
]


# JSONB columns that need to become plain JSON on SQLite.
_JSON_COLUMNS = [
    (Template.__table__, "dashboard_def"),
    (Template.__table__, "rules_def"),
]


def _prepare_tables_for_sqlite() -> None:
    for table in _TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())
    for table, column in _JSON_COLUMNS:
        table.c[column].type = JSON()
    # The duplicate-gmail fraud heuristic flags records that share a Gmail
    # identity; the production UNIQUE(referred_gmail) constraint normally
    # prevents that, but legacy/unconstrained rows can exist. Drop the unique
    # index on the in-memory table so the fraud scenario can be seeded.
    Referral.__table__.indexes = {
        ix for ix in Referral.__table__.indexes if not ix.unique
    }
    for constraint in list(Referral.__table__.constraints):
        if getattr(constraint, "name", None) == "referred_gmail":
            Referral.__table__.constraints.discard(constraint)


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


@pytest.fixture()
def engine():
    _prepare_tables_for_sqlite()
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
def client(session_factory, monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth(role: str = ROLE_SUPER_ADMIN, org_id: str | None = None) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=str(uuid.uuid4()),
        org_id=org_id or str(uuid.uuid4()),
        role=role,
        settings=_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Coupons (Req 26)
# ---------------------------------------------------------------------------
def test_coupon_crud_lifecycle(client):
    headers = _auth()
    # Create
    created = client.post(
        _url("/admin/coupons"),
        headers=headers,
        json={"code": "SAVE20", "discount_type": "percent", "value": 20},
    )
    assert created.status_code == 201, created.text
    coupon = created.json()
    assert coupon["code"] == "SAVE20"
    assert coupon["active"] is True
    coupon_id = coupon["id"]

    # List
    listed = client.get(_url("/admin/coupons"), headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Get
    got = client.get(_url(f"/admin/coupons/{coupon_id}"), headers=headers)
    assert got.status_code == 200
    assert got.json()["code"] == "SAVE20"

    # Update
    updated = client.patch(
        _url(f"/admin/coupons/{coupon_id}"),
        headers=headers,
        json={"value": 30, "active": False},
    )
    assert updated.status_code == 200, updated.text
    assert Decimal(str(updated.json()["value"])) == Decimal("30")
    assert updated.json()["active"] is False

    # Delete
    deleted = client.delete(_url(f"/admin/coupons/{coupon_id}"), headers=headers)
    assert deleted.status_code == 204
    assert client.get(_url(f"/admin/coupons/{coupon_id}"), headers=headers).status_code == 404


def test_coupon_requires_super_admin(client):
    resp = client.post(
        _url("/admin/coupons"),
        headers=_auth(role=ROLE_PROJECT_CENTER),
        json={"code": "X", "discount_type": "fixed", "value": 10},
    )
    assert resp.status_code == 403


def test_coupon_duplicate_code_rejected(client):
    headers = _auth()
    body = {"code": "DUP", "discount_type": "fixed", "value": 10}
    assert client.post(_url("/admin/coupons"), headers=headers, json=body).status_code == 201
    dup = client.post(_url("/admin/coupons"), headers=headers, json=body)
    assert dup.status_code == 422
    assert dup.json()["error_code"] == "coupon_code_exists"


def test_coupon_invalid_percent_rejected(client):
    resp = client.post(
        _url("/admin/coupons"),
        headers=_auth(),
        json={"code": "BIG", "discount_type": "percent", "value": 150},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_coupon_value"


# ---------------------------------------------------------------------------
# Commission override (Req 26.1, 26.2)
# ---------------------------------------------------------------------------
@pytest.fixture()
async def org_id(session_factory) -> str:
    async with session_factory() as s:
        org = Organization(name="Partner Co", type="project_center", plan="pro")
        s.add(org)
        await s.flush()
        await s.commit()
        return str(org.id)


async def test_commission_override_including_zero(client, org_id):
    headers = _auth()
    # Set an explicit zero override (valid "no commission" setting, Req 26.1).
    resp = client.patch(
        _url(f"/admin/partners/{org_id}/commission"),
        headers=headers,
        json={"rate": 0},
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["commission_rate_override"])) == Decimal("0")

    # Override a positive rate (Req 26.2).
    resp = client.patch(
        _url(f"/admin/partners/{org_id}/commission"),
        headers=headers,
        json={"rate": 75},
    )
    assert Decimal(str(resp.json()["commission_rate_override"])) == Decimal("75")

    # Clear the override (null -> back to default).
    resp = client.patch(
        _url(f"/admin/partners/{org_id}/commission"),
        headers=headers,
        json={"rate": None},
    )
    assert resp.json()["commission_rate_override"] is None


async def test_commission_override_negative_rejected(client, org_id):
    resp = client.patch(
        _url(f"/admin/partners/{org_id}/commission"),
        headers=_auth(),
        json={"rate": -5},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_commission_rate"


def test_commission_override_unknown_org(client):
    resp = client.patch(
        _url(f"/admin/partners/{uuid.uuid4()}/commission"),
        headers=_auth(),
        json={"rate": 10},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Referral tracking with fraud flags (Req 26.4)
# ---------------------------------------------------------------------------
async def test_referral_fraud_flags(client, session_factory):
    async with session_factory() as s:
        org = Organization(name="Acme")
        s.add(org)
        await s.flush()
        u1 = User(org_id=org.id, email="a@example.com", role=ROLE_PROJECT_CENTER)
        u2 = User(org_id=org.id, email="b@example.com", role=ROLE_PROJECT_CENTER)
        s.add_all([u1, u2])
        await s.flush()
        # Self-referral (referrer == referred).
        s.add(
            Referral(
                referrer_user_id=u1.id,
                referred_user_id=u1.id,
                referred_gmail="self@gmail.com",
                status="confirmed",
            )
        )
        # Duplicate gmail across two records.
        s.add(
            Referral(
                referrer_user_id=u1.id,
                referred_user_id=u2.id,
                referred_gmail="dup@gmail.com",
                status="confirmed",
            )
        )
        s.add(
            Referral(
                referrer_user_id=u2.id,
                referred_user_id=None,
                referred_gmail="dup@gmail.com",
                status="pending",
            )
        )
        await s.commit()

    resp = client.get(_url("/admin/referrals"), headers=_auth())
    assert resp.status_code == 200, resp.text
    records = resp.json()
    assert len(records) == 3
    by_gmail = {}
    for r in records:
        by_gmail.setdefault(r["referred_gmail"], []).append(r)

    self_rec = by_gmail["self@gmail.com"][0]
    assert self_rec["fraud_flags"]["self_referral"] is True
    assert self_rec["fraud"] is True

    for r in by_gmail["dup@gmail.com"]:
        assert r["fraud_flags"]["duplicate_gmail"] is True
        assert r["fraud"] is True


# ---------------------------------------------------------------------------
# Template CRUD (Req 27.2)
# ---------------------------------------------------------------------------
def test_template_crud_lifecycle(client):
    headers = _auth()
    created = client.post(
        _url("/admin/templates"),
        headers=headers,
        json={
            "category": "student",
            "name": "Temperature Monitor",
            "arduino_code": "void setup(){}",
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["category"] == "student"

    # Edit name + clear arduino_code via explicit null.
    updated = client.patch(
        _url(f"/admin/templates/{template_id}"),
        headers=headers,
        json={"name": "Temp Monitor v2", "arduino_code": None},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Temp Monitor v2"
    assert updated.json()["arduino_code"] is None

    # Delete
    assert client.delete(_url(f"/admin/templates/{template_id}"), headers=headers).status_code == 204


def test_template_invalid_category_rejected(client):
    resp = client.post(
        _url("/admin/templates"),
        headers=_auth(),
        json={"category": "bogus", "name": "X"},
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_template_category"


def test_template_requires_super_admin(client):
    resp = client.post(
        _url("/admin/templates"),
        headers=_auth(role=ROLE_PROJECT_CENTER),
        json={"category": "student", "name": "X"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Notification settings (Req 27.3) + site analytics (Req 27.1)
# ---------------------------------------------------------------------------
def test_notification_settings_read_and_update(client):
    headers = _auth()
    initial = client.get(_url("/admin/notification-settings"), headers=headers)
    assert initial.status_code == 200
    assert "telegram" in initial.json()

    updated = client.patch(
        _url("/admin/notification-settings"),
        headers=headers,
        json={"telegram": {"enabled": True, "bot_token": "abc"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["telegram"]["enabled"] is True
    assert updated.json()["telegram"]["bot_token"] == "abc"


def test_site_analytics(client):
    resp = client.get(_url("/admin/site-analytics"), headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert "page_views" in body
    assert "visitors" in body
    assert "sessions" in body


def test_notification_settings_requires_super_admin(client):
    resp = client.get(
        _url("/admin/notification-settings"), headers=_auth(role=ROLE_PROJECT_CENTER)
    )
    assert resp.status_code == 403
