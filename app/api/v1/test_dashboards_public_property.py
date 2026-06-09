"""Property-based test for public dashboard read-only enforcement (Task 8.4).

# Feature: iotaps-platform, Property 16: Public dashboard links are strictly read-only

Property 16 (design.md "Correctness Properties"):

    For a dashboard shared via a Public_Dashboard_Link, a GET through the public
    token returns read-only dashboard data while sharing is enabled; once
    sharing is disabled the token never resolves again (not-available / 404);
    and any mutating HTTP verb submitted to the public path is rejected
    (405 Method Not Allowed) regardless of token state.

Validates: Requirements 8.2, 8.3, 8.4

The test drives the real FastAPI app end to end against an in-memory SQLite DB
(via a ``get_session`` dependency override), mirroring the in-memory pattern in
``test_dashboards_endpoints.py``. For each Hypothesis example it generates a
random sequence of share / unshare / public-read / mutate operations against a
single dashboard and asserts the invariant holds after every step. No live
Postgres/Redis/MQTT is required.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_PROJECT_CENTER
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.dashboard import Dashboard, Widget
from app.models.organization import Organization
from app.models.user import User

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    User.__table__,
    Dashboard.__table__,
    Widget.__table__,
]

# Mutating HTTP verbs that must always be rejected on the public path (Req 8.4).
_MUTATING_VERBS = ("post", "patch", "delete", "put")

# The set of operations a generated scenario can perform on the dashboard.
_OPERATIONS = ("share", "unshare", "read", *(f"mutate_{v}" for v in _MUTATING_VERBS))


def _prepare_tables() -> None:
    """Adapt the Postgres-flavoured ORM tables for the SQLite test engine."""
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    # JSONB -> JSON for SQLite-backed tests.
    Dashboard.__table__.c.layout.type = JSON()
    Widget.__table__.c.config.type = JSON()
    Widget.__table__.c.layout.type = JSON()
    Widget.__table__.c.annotations.type = JSON()
    # Boolean columns carry Postgres server_defaults; give SQLite python-side
    # defaults so inserts that omit them succeed.
    Dashboard.__table__.c.is_public.server_default = None
    Dashboard.__table__.c.is_public.default = ColumnDefault(False)
    Widget.__table__.c.pinned.server_default = None
    Widget.__table__.c.pinned.default = ColumnDefault(False)
    Widget.__table__.c.annotations.server_default = None
    Widget.__table__.c.annotations.default = ColumnDefault(list)


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


def _auth(user_id: str, org_id: str, role: str) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=_settings()
    )
    return {"Authorization": f"Bearer {token}"}


def _url(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


async def _seed_dashboard(session_factory) -> dict[str, str]:
    """Create an org, an owning Project_Center user, and one dashboard."""
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="pro")
        s.add(org)
        await s.flush()
        owner = User(
            org_id=org.id,
            email=f"pc-{uuid.uuid4().hex[:8]}@example.com",
            role=ROLE_PROJECT_CENTER,
        )
        s.add(owner)
        await s.flush()
        dashboard = Dashboard(org_id=org.id, owner_user_id=owner.id, name="Shared")
        s.add(dashboard)
        await s.flush()  # populate dashboard.id before the widget references it
        # One widget so the read-only payload carries content.
        s.add(
            Widget(
                org_id=org.id,
                dashboard_id=dashboard.id,
                type="gauge",
                config={"metric": "temp"},
            )
        )
        await s.commit()
        return {
            "org_id": str(org.id),
            "owner_id": str(owner.id),
            "dash_id": str(dashboard.id),
        }


def _build_client(monkeypatch) -> tuple[TestClient, dict[str, str]]:
    """Build a fresh app + in-memory DB + seeded dashboard for one example."""
    _prepare_tables()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import asyncio

    async def _init() -> dict[str, str]:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=_TABLES)
            )
        return await _seed_dashboard(factory)

    ctx = asyncio.run(_init())

    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    app = create_app()

    async def _override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)
    client._iotaps_engine = engine  # keep a handle for disposal
    return client, ctx


def _dispose(client: TestClient) -> None:
    import asyncio

    engine = getattr(client, "_iotaps_engine", None)
    if engine is not None:
        asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# Generator: a random sequence of operations against the dashboard.
# ---------------------------------------------------------------------------
_scenario = st.lists(st.sampled_from(_OPERATIONS), min_size=1, max_size=12)


def _assert_read_only_payload(body: dict, dash_id: str) -> None:
    """A public GET returns the dashboard read-only with no tenant identifiers."""
    assert body["dashboard"]["id"] == dash_id
    assert body["dashboard"]["name"] == "Shared"
    # Read-only projection must not leak tenant identifiers (Req 8.2).
    assert "org_id" not in body["dashboard"]
    assert "owner_user_id" not in body["dashboard"]
    for widget in body["widgets"]:
        assert "org_id" not in widget


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(operations=_scenario)
def test_public_dashboard_read_only_enforcement(monkeypatch, operations):
    """Property 16: public dashboard links are strictly read-only.

    Validates: Requirements 8.2, 8.3, 8.4
    """
    client, ctx = _build_client(monkeypatch)
    try:
        dash_id = ctx["dash_id"]
        headers = _auth(ctx["owner_id"], ctx["org_id"], ROLE_PROJECT_CENTER)
        share_url = _url(f"/dashboards/{dash_id}/share")

        def public_url(token: str) -> str:
            return _url(f"/public/dashboards/{token}")

        sharing = False
        current_token: str | None = None
        seen_tokens: set[str] = set()

        for op in operations:
            if op == "share":
                resp = client.post(share_url, headers=headers)
                assert resp.status_code == 200, resp.text
                current_token = resp.json()["public_token"]
                assert current_token
                seen_tokens.add(current_token)
                sharing = True

            elif op == "unshare":
                resp = client.delete(share_url, headers=headers)
                assert resp.status_code == 204, resp.text
                sharing = False
                current_token = None

            elif op == "read":
                # While sharing is enabled, the live token serves read-only data.
                if sharing and current_token is not None:
                    resp = client.get(public_url(current_token))
                    assert resp.status_code == 200, resp.text
                    _assert_read_only_payload(resp.json(), dash_id)
                # Every token that is not the live one must no longer resolve
                # (sharing disabled => not-available, Req 8.3).
                for token in seen_tokens:
                    if sharing and token == current_token:
                        continue
                    stale = client.get(public_url(token))
                    assert stale.status_code == 404, stale.text

            else:  # mutate_<verb>
                verb = op.split("_", 1)[1]
                # Target the live token when present, otherwise any token value;
                # a mutating verb on the public path is always rejected (Req 8.4).
                token = current_token or "no-such-token"
                resp = getattr(client, verb)(public_url(token))
                assert resp.status_code == 405, (
                    f"{verb} on public path must be 405, got {resp.status_code}"
                )

        # Final invariant: after disabling, the token can never resolve again.
        if not sharing:
            for token in seen_tokens:
                assert client.get(public_url(token)).status_code == 404
    finally:
        _dispose(client)
