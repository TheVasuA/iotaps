"""Endpoint tests for the Super_Admin control panel (Task 20.1, Req 23.1-23.6).

Exercises the admin router end to end against an in-memory SQLite database (via
a dependency override) and a fake in-memory Redis (patched into ``get_redis``).
No live Postgres/Redis is required.

Covered acceptance criteria:
  - 23.1 overview returns counts, online, revenue, server health
  - 23.2 create / suspend / delete company applies to the Organization
  - 23.3 suspended org denies new sign-ins; existing tokens keep working
  - 23.4 reset a user's password across any organization
  - 23.5 change a user's role
  - 23.6 reassign a device across organization boundaries
  - Super_Admin-only: non-admins are forbidden
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

import app.api.v1.admin as admin_module
import app.api.v1.auth as auth_module
import app.models  # noqa: F401  (register all models on Base.metadata)
from app.core.config import Settings
from app.core.redis_keys import ONLINE_DEVICES
from app.core.security import jwt as jwt_service
from app.core.security import password as password_service
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.billing import Payment, Subscription
from app.models.device import Device
from app.models.infra import MqttNode
from app.models.organization import Organization
from app.models.user import User

_TABLES = [
    Organization.__table__,
    User.__table__,
    Device.__table__,
    MqttNode.__table__,
    Subscription.__table__,
    Payment.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


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
def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(admin_module, "get_redis", lambda: client)
    monkeypatch.setattr(auth_module, "get_redis", lambda: client)
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    return client


@pytest.fixture()
def client(session_factory, fake_redis, monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", _settings)
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
# Seed helpers
# ---------------------------------------------------------------------------
async def _seed_org(session_factory, **overrides) -> Organization:
    async with session_factory() as s:
        defaults = dict(
            name="Org", type="project_center", plan="free", status="active"
        )
        defaults.update(overrides)
        org = Organization(**defaults)
        s.add(org)
        await s.commit()
        await s.refresh(org)
        return org


async def _seed_user(session_factory, org_id, **overrides) -> User:
    async with session_factory() as s:
        defaults = dict(
            org_id=org_id,
            email=f"u{uuid.uuid4().hex[:8]}@example.com",
            password_hash=password_service.hash_password("s3cret-password"),
            password_format=password_service.CURRENT_FORMAT,
            role=ROLE_PROJECT_CENTER,
            twofa_enabled=False,
            theme_mode="light",
        )
        defaults.update(overrides)
        user = User(**defaults)
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


async def _seed_device(session_factory, org_id, **overrides) -> Device:
    async with session_factory() as s:
        defaults = dict(org_id=org_id, label="Dev", status="offline")
        defaults.update(overrides)
        device = Device(**defaults)
        s.add(device)
        await s.commit()
        await s.refresh(device)
        return device


# ---------------------------------------------------------------------------
# Auth / RBAC
# ---------------------------------------------------------------------------
def test_overview_requires_auth(client):
    assert client.get(_url("/admin/overview")).status_code == 401


def test_overview_forbidden_for_non_admin(client):
    resp = client.get(_url("/admin/overview"), headers=_auth(role=ROLE_PROJECT_CENTER))
    assert resp.status_code == 403


def test_create_company_forbidden_for_device_user(client):
    resp = client.post(
        _url("/admin/companies"),
        json={"name": "Acme"},
        headers=_auth(role=ROLE_DEVICE_USER),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Overview (Req 23.1)
# ---------------------------------------------------------------------------
async def _seed_overview(session_factory):
    org = await _seed_org(session_factory)
    await _seed_user(session_factory, org.id)
    device = await _seed_device(session_factory, org.id)
    async with session_factory() as s:
        s.add(MqttNode(ip="10.0.0.1", port=1883, capacity=1000, active_connections=5))
        sub = Subscription(org_id=org.id, plan="pro", status="active")
        s.add(sub)
        await s.flush()
        s.add(
            Payment(
                org_id=org.id,
                subscription_id=sub.id,
                amount=Decimal("500"),
                currency="INR",
                status="captured",
            )
        )
        # A non-captured payment must not count towards revenue.
        s.add(
            Payment(
                org_id=org.id,
                subscription_id=sub.id,
                amount=Decimal("999"),
                currency="INR",
                status="created",
            )
        )
        await s.commit()
    return org, device


def test_overview_returns_platform_metrics(client, session_factory, fake_redis):
    import asyncio

    org, device = asyncio.get_event_loop().run_until_complete(
        _seed_overview(session_factory)
    )
    # Mark the device online in the presence set.
    asyncio.get_event_loop().run_until_complete(
        fake_redis.sadd(ONLINE_DEVICES, str(device.id))
    )

    resp = client.get(_url("/admin/overview"), headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["companies"] == 1
    assert body["devices"] == 1
    assert body["users"] == 1
    assert body["online"] == 1
    assert Decimal(str(body["revenue"])) == Decimal("500")
    assert body["server_health"]["redis"] == "ok"
    assert len(body["server_health"]["mqtt_nodes"]) == 1


# ---------------------------------------------------------------------------
# Company management (Req 23.2)
# ---------------------------------------------------------------------------
def test_create_company(client):
    resp = client.post(
        _url("/admin/companies"), json={"name": "Acme Corp"}, headers=_auth()
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert body["status"] == "active"


def test_create_company_rejects_blank_name(client):
    resp = client.post(_url("/admin/companies"), json={"name": "   "}, headers=_auth())
    assert resp.status_code == 422


def test_suspend_company(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    resp = client.patch(
        _url(f"/admin/companies/{org.id}/suspend"), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"


def test_delete_company(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    resp = client.delete(_url(f"/admin/companies/{org.id}"), headers=_auth())
    assert resp.status_code == 204
    # Subsequent suspend should now 404.
    again = client.patch(_url(f"/admin/companies/{org.id}/suspend"), headers=_auth())
    assert again.status_code == 404


def test_suspend_unknown_company_404(client):
    resp = client.patch(
        _url(f"/admin/companies/{uuid.uuid4()}/suspend"), headers=_auth()
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Suspension gates new sign-ins, existing sessions continue (Req 23.3)
# ---------------------------------------------------------------------------
def test_suspended_org_denies_new_login(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    user = asyncio.get_event_loop().run_until_complete(
        _seed_user(session_factory, org.id, email="member@example.com")
    )

    # Login works while active.
    ok = client.post(
        _url("/auth/login"),
        json={"email": "member@example.com", "password": "s3cret-password"},
    )
    assert ok.status_code == 200, ok.text

    # Suspend the org.
    client.patch(_url(f"/admin/companies/{org.id}/suspend"), headers=_auth())

    # New sign-in is denied.
    denied = client.post(
        _url("/auth/login"),
        json={"email": "member@example.com", "password": "s3cret-password"},
    )
    assert denied.status_code == 401
    assert denied.json()["error_code"] == "organization_suspended"


def test_suspended_org_existing_session_continues(client, session_factory):
    """A token issued before suspension keeps working (Req 23.3)."""
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    device = asyncio.get_event_loop().run_until_complete(
        _seed_device(session_factory, org.id)
    )

    # Suspend the org.
    client.patch(_url(f"/admin/companies/{org.id}/suspend"), headers=_auth())

    # An access token for a user in that org (an "existing session") still
    # authorizes API calls - suspension only blocks the login endpoint.
    headers = _auth(role=ROLE_PROJECT_CENTER, org_id=str(org.id))
    resp = client.get(_url(f"/devices/{device.id}"), headers=headers)
    # The request is authenticated (not 401); resource access is governed by the
    # normal tenant rules, not the suspension.
    assert resp.status_code != 401


# ---------------------------------------------------------------------------
# User management (Req 23.4, 23.5)
# ---------------------------------------------------------------------------
def test_reset_user_password(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    user = asyncio.get_event_loop().run_until_complete(
        _seed_user(session_factory, org.id, email="reset@example.com")
    )

    resp = client.post(
        _url(f"/admin/users/{user.id}/reset-password"),
        json={"new_password": "brand-new-pass"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text

    # The new password works at login.
    login = client.post(
        _url("/auth/login"),
        json={"email": "reset@example.com", "password": "brand-new-pass"},
    )
    assert login.status_code == 200, login.text


def test_change_user_role(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    user = asyncio.get_event_loop().run_until_complete(
        _seed_user(session_factory, org.id)
    )
    resp = client.patch(
        _url(f"/admin/users/{user.id}/role"),
        json={"role": ROLE_SUPER_ADMIN},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == ROLE_SUPER_ADMIN


def test_change_user_role_rejects_invalid(client, session_factory):
    import asyncio

    org = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    user = asyncio.get_event_loop().run_until_complete(
        _seed_user(session_factory, org.id)
    )
    resp = client.patch(
        _url(f"/admin/users/{user.id}/role"),
        json={"role": "wizard"},
        headers=_auth(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Device reassignment across org boundaries (Req 23.6)
# ---------------------------------------------------------------------------
def test_reassign_device_across_orgs(client, session_factory):
    import asyncio

    org_a = asyncio.get_event_loop().run_until_complete(
        _seed_org(session_factory, name="A")
    )
    org_b = asyncio.get_event_loop().run_until_complete(
        _seed_org(session_factory, name="B")
    )
    device = asyncio.get_event_loop().run_until_complete(
        _seed_device(session_factory, org_a.id)
    )

    resp = client.post(
        _url(f"/admin/devices/{device.id}/reassign"),
        json={"org_id": str(org_b.id)},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["org_id"] == str(org_b.id)


def test_reassign_device_unknown_target_404(client, session_factory):
    import asyncio

    org_a = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    device = asyncio.get_event_loop().run_until_complete(
        _seed_device(session_factory, org_a.id)
    )
    resp = client.post(
        _url(f"/admin/devices/{device.id}/reassign"),
        json={"org_id": str(uuid.uuid4())},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_reassign_requires_super_admin(client, session_factory):
    import asyncio

    org_a = asyncio.get_event_loop().run_until_complete(_seed_org(session_factory))
    device = asyncio.get_event_loop().run_until_complete(
        _seed_device(session_factory, org_a.id)
    )
    resp = client.post(
        _url(f"/admin/devices/{device.id}/reassign"),
        json={"org_id": str(org_a.id)},
        headers=_auth(role=ROLE_PROJECT_CENTER),
    )
    assert resp.status_code == 403
