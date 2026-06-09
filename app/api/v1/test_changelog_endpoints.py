"""Endpoint tests for the Changelog API + "What's new" popup (Task 19.5, Req 22).

Exercises publishing changelog entries (Req 22.1) and the unseen/seen popup
feed (Req 22.2) end to end against an in-memory SQLite database (dependency
override). No live Postgres/Redis is required.
"""

from __future__ import annotations

import datetime
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
from app.models.ops import Changelog
from app.models.organization import Organization
from app.models.user import User

_TABLES = [
    Organization.__table__,
    User.__table__,
    Changelog.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    for table in _TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


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
    """Create an org + user, returning (user_id, org_id, last_seen setter helper)."""

    async def _create(role: str, last_seen=None) -> tuple[str, str]:
        async with session_factory() as s:
            org = Organization(name="Acme")
            s.add(org)
            await s.flush()
            user = User(
                org_id=org.id,
                email=f"{uuid.uuid4().hex[:8]}@example.com",
                role=role,
                last_changelog_seen_at=last_seen,
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
# Publishing (Req 22.1)
# ---------------------------------------------------------------------------
async def test_publish_requires_super_admin(client, user_factory):
    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    resp = client.post(
        _url("/admin/changelog"),
        headers=headers,
        json={"version": "1.0", "title": "Launch", "body": "Hello"},
    )
    assert resp.status_code == 403


async def test_publish_then_listed(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)

    resp = client.post(
        _url("/admin/changelog"),
        headers=headers,
        json={"version": "1.0", "title": "Launch", "body": "First release"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["published_at"] is not None

    listed = client.get(_url("/changelog"), headers=headers)
    assert listed.status_code == 200
    entries = listed.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["title"] == "Launch"


async def test_publish_empty_rejected(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    resp = client.post(_url("/admin/changelog"), headers=headers, json={})
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "changelog_empty"


async def test_draft_entry_not_listed(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    resp = client.post(
        _url("/admin/changelog"),
        headers=headers,
        json={"title": "Draft", "publish": False},
    )
    assert resp.status_code == 201
    assert resp.json()["published_at"] is None
    listed = client.get(_url("/changelog"), headers=headers).json()["entries"]
    assert listed == []


# ---------------------------------------------------------------------------
# "What's new" popup feed (Req 22.2)
# ---------------------------------------------------------------------------
async def test_new_user_sees_all_published(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    admin_headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    client.post(
        _url("/admin/changelog"),
        headers=admin_headers,
        json={"version": "1.0", "title": "Launch"},
    )

    # A fresh user (no last_changelog_seen_at) sees the entry -> popup shows.
    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    user_headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    unseen = client.get(_url("/changelog/unseen"), headers=user_headers).json()
    assert unseen["show_popup"] is True
    assert len(unseen["entries"]) == 1


async def test_seen_then_no_popup(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    admin_headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    client.post(
        _url("/admin/changelog"),
        headers=admin_headers,
        json={"version": "1.0", "title": "Launch"},
    )

    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    user_headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)

    # Popup shows before viewing.
    assert client.get(_url("/changelog/unseen"), headers=user_headers).json()[
        "show_popup"
    ]

    # Mark seen, then the popup no longer shows.
    seen = client.post(_url("/changelog/seen"), headers=user_headers)
    assert seen.status_code == 200
    after = client.get(_url("/changelog/unseen"), headers=user_headers).json()
    assert after["show_popup"] is False
    assert after["entries"] == []


async def test_entry_published_after_seen_triggers_popup(client, user_factory):
    admin_id, admin_org = await user_factory(ROLE_SUPER_ADMIN)
    admin_headers = _auth_for(admin_id, admin_org, ROLE_SUPER_ADMIN)
    client.post(
        _url("/admin/changelog"),
        headers=admin_headers,
        json={"version": "1.0", "title": "Launch"},
    )

    user_id, org_id = await user_factory(ROLE_DEVICE_USER)
    user_headers = _auth_for(user_id, org_id, ROLE_DEVICE_USER)
    client.post(_url("/changelog/seen"), headers=user_headers)
    assert not client.get(_url("/changelog/unseen"), headers=user_headers).json()[
        "show_popup"
    ]

    # A newer entry is published -> the popup should reappear for just that one.
    client.post(
        _url("/admin/changelog"),
        headers=admin_headers,
        json={"version": "1.1", "title": "Update"},
    )
    unseen = client.get(_url("/changelog/unseen"), headers=user_headers).json()
    assert unseen["show_popup"] is True
    assert len(unseen["entries"]) == 1
    assert unseen["entries"][0]["title"] == "Update"


async def test_unseen_requires_auth(client):
    assert client.get(_url("/changelog/unseen")).status_code == 401
