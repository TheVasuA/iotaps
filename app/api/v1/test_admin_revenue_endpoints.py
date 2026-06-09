"""Endpoint tests for the admin revenue analytics API (Task 20.3, Req 25.1, 25.2).

Exercises GET /admin/revenue end to end against an in-memory SQLite DB:

    - returns the full {mrr, arr, churn, funnel, arpu, by_source, top_orgs} shape
    - requires authentication (401 without a token)
    - Super_Admin-only: a Project_Center is forbidden (403)
    - metrics reflect newly recorded billing data (Req 25.2)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.billing import Payment, Subscription
from app.models.organization import Organization

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
async def seeded(session_factory):
    async with session_factory() as s:
        org = Organization(name="Alpha", type="project_center", plan="pro")
        s.add(org)
        await s.flush()
        sub = Subscription(
            org_id=org.id, plan="pro", billing_cycle="monthly",
            device_count=5, unit_price=99, status="active",
        )
        s.add(sub)
        await s.flush()
        s.add(Payment(
            org_id=org.id, subscription_id=sub.id, amount=Decimal("495"),
            status="captured",
        ))
        await s.commit()
        return {"org_id": str(org.id)}


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


def test_revenue_requires_auth(client):
    assert client.get(_url("/admin/revenue")).status_code == 401


def test_revenue_requires_super_admin(client, seeded):
    resp = client.get(
        _url("/admin/revenue"),
        headers=_auth(role=ROLE_PROJECT_CENTER, org_id=seeded["org_id"]),
    )
    assert resp.status_code == 403


def test_revenue_returns_full_shape(client, seeded):
    resp = client.get(_url("/admin/revenue"), headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "mrr", "arr", "churn", "funnel", "arpu", "by_source", "top_orgs"
    }
    assert body["mrr"] == pytest.approx(495.0)
    assert body["arr"] == pytest.approx(495.0 * 12)
    assert body["arpu"] == pytest.approx(495.0)
    assert body["funnel"]["paying"] == 1
    assert body["by_source"]["monthly"] == pytest.approx(495.0)
    assert body["top_orgs"][0]["org_id"] == seeded["org_id"]


def test_revenue_reflects_new_data(client, seeded, session_factory):
    first = client.get(_url("/admin/revenue"), headers=_auth()).json()

    async def _add_subscription():
        async with session_factory() as s:
            org = Organization(name="Beta", type="project_center", plan="pro")
            s.add(org)
            await s.flush()
            s.add(Subscription(
                org_id=org.id, plan="pro", billing_cycle="monthly",
                device_count=10, unit_price=99, status="active",
            ))
            await s.commit()

    import asyncio

    asyncio.get_event_loop().run_until_complete(_add_subscription())

    second = client.get(_url("/admin/revenue"), headers=_auth()).json()
    assert second["mrr"] == pytest.approx(first["mrr"] + 990.0)
