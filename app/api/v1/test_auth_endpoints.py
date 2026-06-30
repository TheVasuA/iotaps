"""Endpoint tests for the Auth_Service (Task 2.3, Req 1.1-1.6, 1.8, 1.9).

Exercises the FastAPI auth router end to end against an in-memory SQLite
database (via a dependency override) and a fake in-memory Redis (patched into
``get_redis``). No live Postgres/Redis is required.

Covered acceptance criteria:
  - 1.1 valid credentials -> access + refresh tokens
  - 1.3 invalid credentials -> authentication error
  - 1.4 refresh -> new access token
  - 1.5 revoked/invalid refresh -> rejected
  - 1.6 logout revokes refresh token
  - 1.8 2FA gate before issuing tokens
  - 1.9 unusable stored password format -> reset required
"""

from __future__ import annotations

import datetime as _dt
import uuid

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.schema import ColumnDefault
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.v1.auth as auth_module
from app.core.security import jwt as jwt_service
from app.core.security import password as password_service
from app.core.security import totp as totp_service
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.organization import Organization
from app.models.user import User

# Import all models so their tables are registered on Base.metadata.
import app.models  # noqa: F401

# Only these two tables are needed for auth tests; creating the full metadata
# would pull in Postgres-specific DDL (JSONB, gen_random_uuid()) unsupported by
# the in-memory SQLite test engine.
_AUTH_TABLES = [Organization.__table__, User.__table__]


def _prepare_tables_for_sqlite() -> None:
    """Replace the Postgres ``gen_random_uuid()`` PK default with a Python one.

    SQLite cannot evaluate ``gen_random_uuid()`` in a column DEFAULT, so we swap
    the server-side default on the ``id`` columns for a client-side ``uuid4``
    default. All other server defaults (booleans, text, CURRENT_TIMESTAMP) are
    SQLite-compatible and left untouched.
    """
    for table in _AUTH_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture()
def engine():
    _prepare_tables_for_sqlite()
    # StaticPool + a single shared connection so the in-memory DB persists
    # across the many sessions opened by separate requests in one test.
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
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_AUTH_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_AUTH_TABLES))


@pytest.fixture()
def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(auth_module, "get_redis", lambda: client)
    monkeypatch.setattr(jwt_service, "get_settings", _patched_settings, raising=False)
    return client


def _patched_settings():
    from app.core.config import Settings

    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=900,
        jwt_refresh_token_ttl_seconds=3600,
    )


@pytest.fixture()
def client(session_factory, fake_redis, monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", _patched_settings)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    # Use the TestClient as a context manager so a single blocking portal (and
    # therefore a single asyncio event loop) is shared across every request in a
    # test. The in-memory FakeRedis binds its internal queues to the loop of
    # first use; without a shared loop, a second redis-touching request (e.g.
    # refresh/logout after login) would run on a fresh loop and raise
    # "bound to a different event loop".
    with TestClient(app) as c:
        yield c


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


# ---------------------------------------------------------------------------
# Helpers to seed users directly
# ---------------------------------------------------------------------------
async def _seed_user(session_factory, **overrides) -> User:
    async with session_factory() as s:
        org = Organization(
            id=uuid.uuid4(), name="Org", type="project_center", plan="free",
            status="active",
        )
        s.add(org)
        await s.flush()
        defaults = dict(
            id=uuid.uuid4(),
            org_id=org.id,
            email="user@example.com",
            password_hash=password_service.hash_password("s3cret-password"),
            password_format=password_service.CURRENT_FORMAT,
            role="project_center",
            twofa_enabled=False,
            theme_mode="light",
        )
        defaults.update(overrides)
        user = User(**defaults)
        s.add(user)
        await s.commit()
        await s.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Register + login (Req 1.1, 1.3)
# ---------------------------------------------------------------------------
def test_register_then_login_issues_tokens(client):
    reg = client.post(
        _url("/auth/register"),
        json={"email": "new@example.com", "password": "hunter2-pass"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["role"] == "project_center"

    login = client.post(
        _url("/auth/login"),
        json={"email": "new@example.com", "password": "hunter2-pass"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    claims = jwt_service.decode_access_token(
        tokens["access_token"], settings=_patched_settings()
    )
    assert claims.role == "project_center"
    assert claims.sub


def test_login_wrong_password_rejected(client):
    client.post(
        _url("/auth/register"),
        json={"email": "a@example.com", "password": "right-password"},
    )
    resp = client.post(
        _url("/auth/login"),
        json={"email": "a@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "authentication_error"


def test_login_unknown_user_rejected(client):
    resp = client.post(
        _url("/auth/login"),
        json={"email": "ghost@example.com", "password": "whatever12"},
    )
    assert resp.status_code == 401


def test_duplicate_register_rejected(client):
    payload = {"email": "dupe@example.com", "password": "password12"}
    assert client.post(_url("/auth/register"), json=payload).status_code == 201
    resp = client.post(_url("/auth/register"), json=payload)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "email_taken"


# ---------------------------------------------------------------------------
# Refresh rotation + logout (Req 1.4, 1.5, 1.6)
# ---------------------------------------------------------------------------
def test_refresh_returns_new_access_token(client):
    client.post(_url("/auth/register"), json={"email": "r@example.com", "password": "password12"})
    tokens = client.post(
        _url("/auth/login"), json={"email": "r@example.com", "password": "password12"}
    ).json()
    resp = client.post(_url("/auth/refresh"), json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


def test_refresh_old_token_rejected_after_rotation(client):
    client.post(_url("/auth/register"), json={"email": "r2@example.com", "password": "password12"})
    tokens = client.post(
        _url("/auth/login"), json={"email": "r2@example.com", "password": "password12"}
    ).json()
    old_refresh = tokens["refresh_token"]
    # First refresh consumes the old token.
    assert client.post(_url("/auth/refresh"), json={"refresh_token": old_refresh}).status_code == 200
    # Reusing it is rejected (Req 1.5).
    again = client.post(_url("/auth/refresh"), json={"refresh_token": old_refresh})
    assert again.status_code == 401
    assert again.json()["error_code"] == "refresh_invalid"


def test_logout_revokes_refresh_token(client):
    client.post(_url("/auth/register"), json={"email": "l@example.com", "password": "password12"})
    tokens = client.post(
        _url("/auth/login"), json={"email": "l@example.com", "password": "password12"}
    ).json()
    refresh = tokens["refresh_token"]
    assert client.post(_url("/auth/logout"), json={"refresh_token": refresh}).status_code == 204
    # After logout the refresh token can no longer be used (Req 1.6).
    resp = client.post(_url("/auth/refresh"), json={"refresh_token": refresh})
    assert resp.status_code == 401


def test_refresh_garbage_token_rejected(client):
    resp = client.post(_url("/auth/refresh"), json={"refresh_token": "not-a-jwt"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2FA gate (Req 1.8)
# ---------------------------------------------------------------------------
def test_login_requires_otp_when_2fa_enabled(client, session_factory):
    import asyncio

    secret = totp_service.generate_secret()
    asyncio.get_event_loop().run_until_complete(
        _seed_user(
            session_factory,
            email="2fa@example.com",
            twofa_enabled=True,
            twofa_secret=secret,
        )
    )
    # Missing OTP -> rejected with a 2FA-required marker.
    resp = client.post(
        _url("/auth/login"),
        json={"email": "2fa@example.com", "password": "s3cret-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "twofa_required"

    # Wrong OTP -> rejected.
    bad = client.post(
        _url("/auth/login"),
        json={"email": "2fa@example.com", "password": "s3cret-password", "otp": "000000"},
    )
    assert bad.status_code == 401
    assert bad.json()["error_code"] == "twofa_invalid"

    # Correct OTP -> tokens issued.
    import pyotp

    good = client.post(
        _url("/auth/login"),
        json={
            "email": "2fa@example.com",
            "password": "s3cret-password",
            "otp": pyotp.TOTP(secret).now(),
        },
    )
    assert good.status_code == 200, good.text
    assert good.json()["access_token"]


# ---------------------------------------------------------------------------
# Force-reset for unusable password format (Req 1.9)
# ---------------------------------------------------------------------------
def test_login_requires_reset_for_legacy_format(client, session_factory):
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        _seed_user(
            session_factory,
            email="legacy@example.com",
            password_hash="plaintext-not-a-hash",
            password_format="md5",
        )
    )
    resp = client.post(
        _url("/auth/login"),
        json={"email": "legacy@example.com", "password": "s3cret-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "password_reset_required"
