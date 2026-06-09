"""Endpoint tests for the Dashboards & Widgets API (Task 8.1, Req 7).

Exercises the FastAPI dashboards router end to end against an in-memory SQLite
DB (via a dependency override). Verifies dashboard/widget CRUD, layout
persistence (React Grid Layout, Req 7.1/7.2), pinned state (Req 7.5), chart
annotations (Req 7.6), partial-PATCH semantics, RBAC, and tenant scoping. No
live Postgres/Redis/MQTT is required.
"""

from __future__ import annotations

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

from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_DEVICE_USER, ROLE_PROJECT_CENTER
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


def _prepare_tables() -> None:
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


async def _seed_org(session_factory, plan: str | None = "pro") -> dict[str, str]:
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan=plan)
        s.add(org)
        await s.flush()
        suffix = uuid.uuid4().hex[:8]
        pc = User(
            org_id=org.id, email=f"pc-{suffix}@example.com", role=ROLE_PROJECT_CENTER
        )
        du = User(
            org_id=org.id, email=f"du-{suffix}@example.com", role=ROLE_DEVICE_USER
        )
        s.add_all([pc, du])
        await s.commit()
        return {"org_id": str(org.id), "pc_id": str(pc.id), "du_id": str(du.id)}


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


def _auth(user_id: str, org_id: str, role: str) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=_settings()
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
async def org(session_factory):
    return await _seed_org(session_factory, "pro")


@pytest.fixture()
async def second_org(session_factory):
    return await _seed_org(session_factory, "pro")


def _create_dashboard(client, headers, name: str = "My Dash", layout=None):
    body: dict = {"name": name}
    if layout is not None:
        body["layout"] = layout
    return client.post(_url("/dashboards"), json=body, headers=headers)


def _add_widget(client, headers, dash_id, type="line", config=None, layout=None):
    body: dict = {"type": type}
    if config is not None:
        body["config"] = config
    if layout is not None:
        body["layout"] = layout
    return client.post(
        _url(f"/dashboards/{dash_id}/widgets"), json=body, headers=headers
    )


# ---------------------------------------------------------------------------
# Dashboard CRUD
# ---------------------------------------------------------------------------
def test_create_and_get_dashboard(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    resp = _create_dashboard(client, headers, "Floor 1")
    assert resp.status_code == 201, resp.text
    dash = resp.json()["dashboard"]
    assert dash["name"] == "Floor 1"
    assert dash["owner_user_id"] == org["pc_id"]
    assert dash["is_public"] is False

    detail = client.get(_url(f"/dashboards/{dash['id']}"), headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["dashboard"]["id"] == dash["id"]
    assert body["widgets"] == []


def test_list_dashboards(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    _create_dashboard(client, headers, "A")
    _create_dashboard(client, headers, "B")
    listing = client.get(_url("/dashboards"), headers=headers)
    assert listing.status_code == 200
    names = {d["name"] for d in listing.json()}
    assert names == {"A", "B"}


def test_create_dashboard_rejects_blank_name(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(_url("/dashboards"), json={"name": "   "}, headers=headers)
    # Pydantic min_length passes on whitespace; service rejects -> 422.
    assert resp.status_code == 422


def test_device_user_can_build_dashboard(client, org):
    headers = _auth(org["du_id"], org["org_id"], ROLE_DEVICE_USER)
    resp = _create_dashboard(client, headers, "Mine")
    assert resp.status_code == 201
    assert resp.json()["dashboard"]["owner_user_id"] == org["du_id"]


# ---------------------------------------------------------------------------
# Layout persistence (Req 7.1, 7.2)
# ---------------------------------------------------------------------------
def test_update_dashboard_persists_layout(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers, "L").json()["dashboard"]["id"]
    grid = {"lg": [{"i": "w1", "x": 0, "y": 0, "w": 4, "h": 3}]}
    resp = client.patch(
        _url(f"/dashboards/{dash_id}"), json={"layout": grid}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["dashboard"]["layout"] == grid

    # Layout survives a re-fetch.
    refetched = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    assert refetched["dashboard"]["layout"] == grid


def test_update_dashboard_partial_patch_preserves_name(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers, "Keep").json()["dashboard"]["id"]
    # Only update layout; name must be preserved.
    client.patch(
        _url(f"/dashboards/{dash_id}"), json={"layout": {"a": 1}}, headers=headers
    )
    body = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    assert body["dashboard"]["name"] == "Keep"
    assert body["dashboard"]["layout"] == {"a": 1}


# ---------------------------------------------------------------------------
# Widget CRUD + state (Req 7.1, 7.3, 7.5, 7.6)
# ---------------------------------------------------------------------------
def test_add_widget(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    layout = {"x": 1, "y": 2, "w": 3, "h": 4}
    resp = _add_widget(
        client, headers, dash_id, type="gauge", config={"metric": "temp"}, layout=layout
    )
    assert resp.status_code == 201, resp.text
    widget = resp.json()["widget"]
    assert widget["type"] == "gauge"
    assert widget["config"] == {"metric": "temp"}
    assert widget["layout"] == layout
    assert widget["pinned"] is False
    assert widget["annotations"] == []


def test_add_widget_rejects_unknown_type(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    resp = _add_widget(client, headers, dash_id, type="hologram")
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_widget_type"


def test_update_widget_layout_pinned_annotations(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    wid = _add_widget(client, headers, dash_id).json()["widget"]["id"]

    new_layout = {"x": 5, "y": 6, "w": 2, "h": 2}
    annotations = [{"ts": "2025-01-01T00:00:00Z", "text": "spike"}]
    resp = client.patch(
        _url(f"/dashboards/{dash_id}/widgets/{wid}"),
        json={"layout": new_layout, "pinned": True, "annotations": annotations},
        headers=headers,
    )
    assert resp.status_code == 200
    widget = resp.json()["widget"]
    assert widget["layout"] == new_layout  # Req 7.2
    assert widget["pinned"] is True  # Req 7.5
    assert widget["annotations"] == annotations  # Req 7.6

    # State survives re-fetch via dashboard detail.
    detail = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    persisted = detail["widgets"][0]
    assert persisted["pinned"] is True
    assert persisted["annotations"] == annotations


def test_update_widget_partial_patch_preserves_other_fields(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    wid = _add_widget(
        client, headers, dash_id, config={"metric": "temp"}
    ).json()["widget"]["id"]
    # Pin only; config must be preserved.
    client.patch(
        _url(f"/dashboards/{dash_id}/widgets/{wid}"),
        json={"pinned": True},
        headers=headers,
    )
    detail = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    widget = detail["widgets"][0]
    assert widget["pinned"] is True
    assert widget["config"] == {"metric": "temp"}


# ---------------------------------------------------------------------------
# Tenant isolation (Req 3.2, 3.3)
# ---------------------------------------------------------------------------
def test_tenant_isolation_lists_only_own_dashboards(client, org, second_org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    _create_dashboard(client, headers, "mine")
    other_headers = _auth(
        second_org["pc_id"], second_org["org_id"], ROLE_PROJECT_CENTER
    )
    _create_dashboard(client, other_headers, "theirs")

    mine = client.get(_url("/dashboards"), headers=headers).json()
    assert [d["name"] for d in mine] == ["mine"]


def test_cannot_access_other_org_dashboard(client, org, second_org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers, "secret").json()["dashboard"]["id"]
    other_headers = _auth(
        second_org["pc_id"], second_org["org_id"], ROLE_PROJECT_CENTER
    )
    resp = client.get(_url(f"/dashboards/{dash_id}"), headers=other_headers)
    assert resp.status_code == 403


def test_cannot_add_widget_to_other_org_dashboard(client, org, second_org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    other_headers = _auth(
        second_org["pc_id"], second_org["org_id"], ROLE_PROJECT_CENTER
    )
    resp = _add_widget(client, other_headers, dash_id)
    assert resp.status_code == 403


def test_requires_authentication(client, org):
    resp = client.get(_url("/dashboards"))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Public shareable dashboards (Req 8.1, 8.2, 8.3, 8.4)
# ---------------------------------------------------------------------------
def test_share_dashboard_generates_public_token(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers, "Shared").json()["dashboard"]["id"]
    resp = client.post(_url(f"/dashboards/{dash_id}/share"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_token"]
    assert body["url"].endswith(f"/public/dashboards/{body['public_token']}")

    # The dashboard now reports public + token via the authenticated detail.
    detail = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    assert detail["dashboard"]["is_public"] is True
    assert detail["dashboard"]["public_token"] == body["public_token"]


def test_share_is_idempotent_preserves_token(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    first = client.post(_url(f"/dashboards/{dash_id}/share"), headers=headers).json()
    second = client.post(_url(f"/dashboards/{dash_id}/share"), headers=headers).json()
    assert first["public_token"] == second["public_token"]


def test_public_dashboard_served_without_auth(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers, "Public").json()["dashboard"]["id"]
    _add_widget(client, headers, dash_id, type="gauge", config={"metric": "temp"})
    token = client.post(
        _url(f"/dashboards/{dash_id}/share"), headers=headers
    ).json()["public_token"]

    # No Authorization header at all (Req 8.2).
    resp = client.get(_url(f"/public/dashboards/{token}"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dashboard"]["id"] == dash_id
    assert body["dashboard"]["name"] == "Public"
    # Tenant identifiers are not exposed on the public payload.
    assert "org_id" not in body["dashboard"]
    assert len(body["widgets"]) == 1
    assert body["widgets"][0]["type"] == "gauge"


def test_public_dashboard_denied_after_unshare(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    token = client.post(
        _url(f"/dashboards/{dash_id}/share"), headers=headers
    ).json()["public_token"]

    # Revoke sharing (Req 8.3).
    revoke = client.delete(_url(f"/dashboards/{dash_id}/share"), headers=headers)
    assert revoke.status_code == 204

    # The previously valid token must no longer resolve.
    resp = client.get(_url(f"/public/dashboards/{token}"))
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"

    # And the dashboard is no longer flagged public.
    detail = client.get(_url(f"/dashboards/{dash_id}"), headers=headers).json()
    assert detail["dashboard"]["is_public"] is False
    assert detail["dashboard"]["public_token"] is None


def test_public_dashboard_unknown_token_not_available(client, org):
    resp = client.get(_url("/public/dashboards/does-not-exist"))
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "not_found"


def test_public_dashboard_rejects_mutating_actions(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    token = client.post(
        _url(f"/dashboards/{dash_id}/share"), headers=headers
    ).json()["public_token"]

    # The public route exposes only GET; any mutating verb is rejected (Req 8.4).
    for verb in ("post", "patch", "delete", "put"):
        resp = getattr(client, verb)(_url(f"/public/dashboards/{token}"))
        assert resp.status_code == 405, f"{verb} should be rejected"


def test_cannot_share_other_org_dashboard(client, org, second_org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    other_headers = _auth(
        second_org["pc_id"], second_org["org_id"], ROLE_PROJECT_CENTER
    )
    resp = client.post(_url(f"/dashboards/{dash_id}/share"), headers=other_headers)
    assert resp.status_code == 403


def test_share_requires_authentication(client, org):
    headers = _auth(org["pc_id"], org["org_id"], ROLE_PROJECT_CENTER)
    dash_id = _create_dashboard(client, headers).json()["dashboard"]["id"]
    resp = client.post(_url(f"/dashboards/{dash_id}/share"))
    assert resp.status_code == 401
