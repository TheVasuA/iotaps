"""Endpoint + service tests for admin health/errors/security/settings (Task 20.5).

Exercises the Super_Admin operational surface from design.md ("Admin",
Req 28-29) end to end against an in-memory SQLite database (dependency
override), plus the error-recording and IP-block service behaviours that the
platform's error handler and auth flow consume.

    GET   /admin/health    -> service statuses                  (Req 28.1)
    GET   /admin/errors    -> recent + trends                   (Req 28.2, 28.3)
    GET   /admin/security  -> login_attempts/blocked_ips/audit  (Req 29.2)
    PATCH /admin/settings  -> applied platform-wide immediately (Req 29.4)
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
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
from app.core.security.principal import ROLE_DEVICE_USER, ROLE_SUPER_ADMIN
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.error_log import ErrorLog
from app.models.organization import Organization
from app.models.security import AuditLog, BlockedIp, LoginAttempt
from app.models.user import User
from app.services import admin_ops_service

_TABLES = [
    Organization.__table__,
    User.__table__,
    ErrorLog.__table__,
    LoginAttempt.__table__,
    BlockedIp.__table__,
    AuditLog.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    from sqlalchemy import JSON

    for table in _TABLES:
        id_col = table.c.get("id")
        if id_col is not None:
            id_col.server_default = None
            id_col.default = ColumnDefault(lambda: uuid.uuid4())
    # JSONB columns have no SQLite compiler; use the generic JSON type.
    ErrorLog.__table__.c.detail.type = JSON()
    AuditLog.__table__.c.detail.type = JSON()


def _settings() -> Settings:
    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=900,
        jwt_refresh_token_ttl_seconds=3600,
    )


@pytest.fixture()
def engine():
    _prepare_tables_for_sqlite()
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield eng


@pytest.fixture()
async def session_factory(engine):
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))


@pytest.fixture()
def client(session_factory, monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


@pytest.fixture()
async def user_factory(session_factory):
    async def _create(role: str) -> tuple[str, str]:
        async with session_factory() as s:
            org = Organization(name="Acme")
            s.add(org)
            await s.flush()
            user = User(
                org_id=org.id,
                email=f"{uuid.uuid4().hex[:8]}@example.com",
                role=role,
            )
            s.add(user)
            await s.flush()
            await s.commit()
            return str(user.id), str(org.id)

    return _create


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth_for(user_id: str, org_id: str, role: str) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=_settings()
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health (Req 28.1)
# ---------------------------------------------------------------------------
async def test_health_requires_super_admin(client, user_factory):
    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    assert client.get(_url("/admin/health"), headers=headers).status_code == 403


async def test_health_lists_service_statuses(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    resp = client.get(_url("/admin/health"), headers=headers)
    assert resp.status_code == 200, resp.text
    services = resp.json()["services"]
    names = {s["name"] for s in services}
    assert "api" in names and "database" in names
    api = next(s for s in services if s["name"] == "api")
    assert api["status"] == "ok"


# ---------------------------------------------------------------------------
# Errors (Req 28.2, 28.3)
# ---------------------------------------------------------------------------
async def test_errors_recent_and_trends(client, user_factory, session_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)

    # Record an error with full user/org/device context (Req 28.2).
    async with session_factory() as s:
        await admin_ops_service.record_error(
            s,
            message="boom",
            error_code="internal_error",
            user_id=admin_id,
            org_id=admin_org,
            device_id=str(uuid.uuid4()),
            detail={"trace": "x"},
        )
        await s.commit()

    resp = client.get(_url("/admin/errors"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["recent"]) == 1
    rec = body["recent"][0]
    assert rec["message"] == "boom"
    assert rec["org_id"] == admin_org
    assert rec["user_id"] == admin_id
    assert rec["device_id"] is not None
    # Trends bucket is continuous (default 7 days) and counts today's error.
    assert len(body["trends"]) == 7
    assert sum(t["count"] for t in body["trends"]) == 1


async def test_errors_requires_super_admin(client, user_factory):
    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    assert client.get(_url("/admin/errors"), headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# Security (Req 29.2)
# ---------------------------------------------------------------------------
async def test_security_overview(client, user_factory, session_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)

    async with session_factory() as s:
        s.add(LoginAttempt(ip="1.2.3.4", email="a@b.com", success=False))
        s.add(BlockedIp(ip="9.9.9.9", reason="abuse"))
        s.add(AuditLog(action="suspend_company"))
        await s.commit()

    resp = client.get(_url("/admin/security"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["login_attempts"]) == 1
    assert body["login_attempts"][0]["ip"] == "1.2.3.4"
    assert len(body["blocked_ips"]) == 1
    assert body["blocked_ips"][0]["ip"] == "9.9.9.9"
    assert len(body["audit_log"]) == 1
    assert body["audit_log"][0]["action"] == "suspend_company"


# ---------------------------------------------------------------------------
# Settings (Req 29.4)
# ---------------------------------------------------------------------------
async def test_patch_settings_applies_immediately(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)

    resp = client.patch(
        _url("/admin/settings"),
        headers=headers,
        json={"updates": {"jwt_access_ttl_seconds": 1200}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["jwt_access_ttl_seconds"] == 1200

    # A subsequent read reflects the new value platform-wide (Req 29.4).
    read = client.get(_url("/admin/settings"), headers=headers)
    assert read.json()["settings"]["jwt_access_ttl_seconds"] == 1200


async def test_patch_settings_requires_super_admin(client, user_factory):
    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    resp = client.patch(
        _url("/admin/settings"),
        headers=headers,
        json={"updates": {"x": 1}},
    )
    assert resp.status_code == 403


async def test_patch_settings_rejects_empty(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    resp = client.patch(
        _url("/admin/settings"), headers=headers, json={"updates": {}}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Resources / backups / marketing (Req 29.1, 29.5, 29.6)
# ---------------------------------------------------------------------------
async def test_resources_backups_marketing(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)

    res = client.get(_url("/admin/resources"), headers=headers)
    assert res.status_code == 200
    assert "storage" in res.json() and "cdn" in res.json()

    backups = client.get(_url("/admin/backups"), headers=headers)
    assert backups.status_code == 200
    assert backups.json()["provider"] == "contabo_snapshots"

    marketing = client.get(_url("/admin/marketing"), headers=headers)
    assert marketing.status_code == 200
    assert "lead_pipeline" in marketing.json()
    assert "marketing_tools" in marketing.json()
