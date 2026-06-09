"""Endpoint tests for admin MQTT node management (Task 20.2, Req 24.1-24.3).

Exercises the ``/admin/mqtt-nodes`` router end to end against an in-memory
SQLite database (via a dependency override). No live Postgres/Redis required.

Covered acceptance criteria:
  - 24.1 register a node by ip/port/capacity -> available for assignment (201)
  - 24.2 deregister a node (204); deregistering an unknown node -> 404
  - 24.3 list nodes with per-node RAM/CPU/disk + active connection metrics
  - Super_Admin-only: non-admins are forbidden (403)
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

import app.api.v1.auth as auth_module
import app.models  # noqa: F401  (register all models on Base.metadata)
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.infra import MqttNode

_TABLES = [MqttNode.__table__]


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
def client(session_factory, monkeypatch):
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


def _auth(role: str = ROLE_SUPER_ADMIN, org_id: str | None = None) -> dict[str, str]:
    token = jwt_service.create_access_token(
        user_id=str(uuid.uuid4()),
        org_id=org_id or str(uuid.uuid4()),
        role=role,
        settings=_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_node(session_factory, **overrides) -> MqttNode:
    async with session_factory() as s:
        defaults = dict(
            ip="10.0.0.1",
            port=1883,
            capacity=1000,
            active_connections=42,
            status="active",
            ram_pct=55.5,
            cpu_pct=30.0,
            disk_pct=12.25,
        )
        defaults.update(overrides)
        node = MqttNode(**defaults)
        s.add(node)
        await s.commit()
        await s.refresh(node)
        return node


# ---------------------------------------------------------------------------
# Auth / RBAC (Super_Admin-only)
# ---------------------------------------------------------------------------
def test_list_requires_auth(client):
    assert client.get(_url("/admin/mqtt-nodes")).status_code == 401


def test_list_forbidden_for_non_admin(client):
    resp = client.get(
        _url("/admin/mqtt-nodes"), headers=_auth(role=ROLE_PROJECT_CENTER)
    )
    assert resp.status_code == 403


def test_register_forbidden_for_device_user(client):
    resp = client.post(
        _url("/admin/mqtt-nodes"),
        json={"ip": "10.0.0.2", "port": 1883, "capacity": 500},
        headers=_auth(role=ROLE_DEVICE_USER),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Register (Req 24.1)
# ---------------------------------------------------------------------------
def test_register_node(client):
    resp = client.post(
        _url("/admin/mqtt-nodes"),
        json={"ip": "10.0.0.5", "port": 8883, "capacity": 2000},
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ip"] == "10.0.0.5"
    assert body["port"] == 8883
    assert body["capacity"] == 2000
    # New node is created active so it is eligible for device assignment.
    assert body["status"] == "active"
    assert body["active_connections"] == 0


def test_register_rejects_invalid_port(client):
    resp = client.post(
        _url("/admin/mqtt-nodes"),
        json={"ip": "10.0.0.5", "port": 70000, "capacity": 100},
        headers=_auth(),
    )
    assert resp.status_code == 422


def test_register_rejects_nonpositive_capacity(client):
    resp = client.post(
        _url("/admin/mqtt-nodes"),
        json={"ip": "10.0.0.5", "port": 1883, "capacity": 0},
        headers=_auth(),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deregister (Req 24.2)
# ---------------------------------------------------------------------------
def test_deregister_node(client, session_factory):
    import asyncio

    node = asyncio.get_event_loop().run_until_complete(_seed_node(session_factory))
    resp = client.delete(_url(f"/admin/mqtt-nodes/{node.id}"), headers=_auth())
    assert resp.status_code == 204

    # It no longer appears in the registry.
    listing = client.get(_url("/admin/mqtt-nodes"), headers=_auth())
    assert listing.status_code == 200
    assert all(n["id"] != str(node.id) for n in listing.json())


def test_deregister_unknown_node_404(client):
    resp = client.delete(
        _url(f"/admin/mqtt-nodes/{uuid.uuid4()}"), headers=_auth()
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List with metrics (Req 24.3)
# ---------------------------------------------------------------------------
def test_list_nodes_exposes_metrics(client, session_factory):
    import asyncio

    node = asyncio.get_event_loop().run_until_complete(_seed_node(session_factory))
    resp = client.get(_url("/admin/mqtt-nodes"), headers=_auth())
    assert resp.status_code == 200, resp.text
    nodes = resp.json()
    assert len(nodes) == 1
    entry = nodes[0]
    assert entry["id"] == str(node.id)
    assert entry["ram_pct"] == 55.5
    assert entry["cpu_pct"] == 30.0
    assert entry["disk_pct"] == 12.25
    assert entry["active_connections"] == 42
    assert entry["capacity"] == 1000
