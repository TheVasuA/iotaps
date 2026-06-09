"""Endpoint tests for the Referral API + register referral wiring (Task 17.1, Req 19).

Exercises GET /referrals end to end and the auth register flow recording a
referral on signup, against an in-memory SQLite database (dependency override)
and a fake in-memory Redis (patched into the auth module). No live
Postgres/Redis is required.
"""

from __future__ import annotations

import uuid

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

import app.api.v1.auth as auth_module
import app.models  # noqa: F401  (register all model tables)
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.organization import Organization
from app.models.referral import Referral, ReferralReward
from app.models.user import User

_TABLES = [
    Organization.__table__,
    User.__table__,
    Referral.__table__,
    ReferralReward.__table__,
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
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(auth_module, "get_redis", lambda: redis)
    monkeypatch.setattr(auth_module, "get_settings", _settings)
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


def _auth_for(user_id: str, org_id: str) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=user_id,
        org_id=org_id,
        role=ROLE_PROJECT_CENTER,
        settings=_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


def test_get_referrals_requires_auth(client):
    assert client.get(_url("/referrals")).status_code == 401


def test_register_with_referral_then_summary(client):
    # Referrer signs up first (its org founds the referral code).
    referrer = client.post(
        _url("/auth/register"),
        json={"email": "referrer@example.com", "password": "password12"},
    ).json()["user"]

    # Read the referrer's code.
    headers = _auth_for(referrer["id"], referrer["org_id"])
    summary = client.get(_url("/referrals"), headers=headers)
    assert summary.status_code == 200, summary.text
    code = summary.json()["code"]
    assert code
    assert summary.json()["count"] == 0
    assert summary.json()["rewards"] == []

    # A friend signs up with the referral code (Req 19.1).
    friend = client.post(
        _url("/auth/register"),
        json={
            "email": "friend@example.com",
            "password": "password12",
            "referral_code": code,
        },
    )
    assert friend.status_code == 201, friend.text

    # The referrer now has 1 confirmed referral and a 1-device/1-month reward.
    summary2 = client.get(_url("/referrals"), headers=headers).json()
    assert summary2["count"] == 1
    assert len(summary2["rewards"]) == 1
    assert summary2["rewards"][0]["devices_granted"] == 1
    assert summary2["rewards"][0]["months_granted"] == 1


def test_register_with_invalid_referral_code_rejected(client):
    resp = client.post(
        _url("/auth/register"),
        json={
            "email": "x@example.com",
            "password": "password12",
            "referral_code": "BOGUS",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "referral_code_invalid"


def test_register_without_referral_code_succeeds(client):
    resp = client.post(
        _url("/auth/register"),
        json={"email": "plain@example.com", "password": "password12"},
    )
    assert resp.status_code == 201, resp.text
