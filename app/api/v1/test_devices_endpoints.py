"""Endpoint tests for the Devices API (Task 4.1, Req 5).

Exercises the FastAPI devices router end to end against an in-memory SQLite DB
(via a dependency override). Verifies provisioning returns credentials + QR,
RBAC denies a Device_User from managing devices, and the QR endpoint returns a
PNG. No live Postgres/Redis/MQTT is required.
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

import app.core.security.deps as deps_module
from app.core.security import jwt as jwt_service
from app.core.config import Settings
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.device import (
    Device,
    DeviceGroup,
    DeviceUserAssignment,
    MqttCredential,
)
from app.models.infra import MqttNode
from app.models.ops import ActivityLog
from app.models.organization import Organization
from app.models.user import User

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    User.__table__,
    MqttNode.__table__,
    DeviceGroup.__table__,
    Device.__table__,
    MqttCredential.__table__,
    DeviceUserAssignment.__table__,
    ActivityLog.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    ActivityLog.__table__.c.detail.type = JSON()


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
    """Seed an org + a Project_Center user + an active MQTT node."""
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        s.add(org)
        await s.flush()
        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        du = User(org_id=org.id, email="du@example.com", role=ROLE_DEVICE_USER)
        node = MqttNode(
            ip="127.0.0.1", port=1883, capacity=100,
            active_connections=0, status="active",
        )
        s.add_all([pc, du, node])
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


def test_provision_device_returns_credentials_and_qr(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(_url("/devices"), json={"label": "Pump"}, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["device"]["label"] == "Pump"
    assert body["device"]["node_id"]  # assigned a node
    # Device-token credential model: a single token serves as both the MQTT
    # username and password, returned once on provisioning (Req 5.1).
    assert body["mqtt_credentials"]["device_token"]
    assert body["mqtt_credentials"]["revoked"] is False
    assert body["device"]["device_token"] == body["mqtt_credentials"]["device_token"]
    assert body["mqtt_credentials"]["acl_pattern"] == f"iotaps/{seeded['org_id']}/#"
    assert seeded["org_id"] in body["qr"]


def test_device_user_cannot_manage_devices(client, seeded):
    headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(_url("/devices"), json={"label": "x"}, headers=headers)
    assert resp.status_code == 403


def test_list_and_get_and_qr_roundtrip(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "A"}, headers=headers).json()
    device_id = created["device"]["id"]

    listed = client.get(_url("/devices"), headers=headers)
    assert listed.status_code == 200
    assert any(d["id"] == device_id for d in listed.json())

    got = client.get(_url(f"/devices/{device_id}"), headers=headers)
    assert got.status_code == 200
    assert got.json()["device"]["id"] == device_id

    qr = client.get(_url(f"/devices/{device_id}/qr"), headers=headers)
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_delete_device_returns_204(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "A"}, headers=headers).json()
    device_id = created["device"]["id"]
    resp = client.delete(_url(f"/devices/{device_id}"), headers=headers)
    assert resp.status_code == 204
    # Gone afterwards (tenant get -> 403 uniform denial).
    assert client.get(_url(f"/devices/{device_id}"), headers=headers).status_code == 403


def test_assign_device_to_user(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "A"}, headers=headers).json()
    device_id = created["device"]["id"]
    resp = client.post(
        _url(f"/devices/{device_id}/assign"),
        json={"user_id": seeded["du_id"]},
        headers=headers,
    )
    assert resp.status_code == 204


def test_start_simulator_sets_interval(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "Sim"}, headers=headers).json()
    device_id = created["device"]["id"]

    resp = client.post(
        _url(f"/devices/{device_id}/simulator"),
        json={"interval_sec": 30},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["device"]
    assert body["is_simulator"] is True
    assert body["sim_interval_sec"] == 30


def test_start_simulator_interval_zero_allowed(client, seeded):
    # interval 0 is a valid configuration meaning "do not publish" (Req 13.3).
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "Sim0"}, headers=headers).json()
    device_id = created["device"]["id"]

    resp = client.post(
        _url(f"/devices/{device_id}/simulator"),
        json={"interval_sec": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["device"]["sim_interval_sec"] == 0


def test_start_simulator_rejects_negative_interval(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "Sim"}, headers=headers).json()
    device_id = created["device"]["id"]

    resp = client.post(
        _url(f"/devices/{device_id}/simulator"),
        json={"interval_sec": -5},
        headers=headers,
    )
    assert resp.status_code == 422


def test_stop_simulator_clears_interval(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(_url("/devices"), json={"label": "Sim"}, headers=headers).json()
    device_id = created["device"]["id"]
    client.post(
        _url(f"/devices/{device_id}/simulator"),
        json={"interval_sec": 30},
        headers=headers,
    )

    resp = client.post(_url(f"/devices/{device_id}/simulator/stop"), headers=headers)
    assert resp.status_code == 204

    got = client.get(_url(f"/devices/{device_id}"), headers=headers).json()["device"]
    assert got["sim_interval_sec"] == 0


def test_device_user_cannot_start_simulator(client, seeded):
    headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url(f"/devices/{uuid.uuid4()}/simulator"),
        json={"interval_sec": 10},
        headers=headers,
    )
    assert resp.status_code == 403
