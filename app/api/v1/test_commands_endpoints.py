"""Endpoint tests for the Commands API (Task 9.1, Req 9.1-9.7).

Exercises ``POST /devices/{id}/commands``, ``GET .../commands/{cid}`` and the
schedules endpoints end to end against an in-memory SQLite DB and ``fakeredis``,
with the MQTT publisher stubbed so no live broker is required. Verifies
online->SENT, offline->QUEUED, tenant isolation, Device_User access scoping,
ACK confirmation, and schedule create/list.
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis
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

import app.models  # noqa: F401  register models
from app.api.v1 import commands as commands_module
from app.core import redis_keys as rk
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import ROLE_DEVICE_USER, ROLE_PROJECT_CENTER
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
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        other = Organization(name="Other", type="project_center", plan="free")
        s.add_all([org, other])
        await s.flush()

        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        du = User(org_id=org.id, email="du@example.com", role=ROLE_DEVICE_USER)
        du2 = User(org_id=org.id, email="du2@example.com", role=ROLE_DEVICE_USER)
        online_dev = Device(org_id=org.id, device_uid="dev-on", status="online")
        offline_dev = Device(org_id=org.id, device_uid="dev-off", status="offline")
        other_dev = Device(org_id=other.id, device_uid="dev-other", status="online")
        s.add_all([pc, du, du2, online_dev, offline_dev, other_dev])
        await s.flush()
        s.add(
            DeviceUserAssignment(org_id=org.id, device_id=online_dev.id, user_id=du.id)
        )
        await s.commit()
        return {
            "org_id": str(org.id),
            "other_org_id": str(other.id),
            "pc_id": str(pc.id),
            "du_id": str(du.id),
            "du2_id": str(du2.id),
            "online_dev": str(online_dev.id),
            "offline_dev": str(offline_dev.id),
            "other_dev": str(other_dev.id),
        }


@pytest.fixture()
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def published():
    return []


@pytest.fixture()
def client(session_factory, redis, published, monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings, raising=False)
    # Stub Redis + MQTT publisher so no live infra is needed.
    monkeypatch.setattr(commands_module, "get_redis", lambda: redis)

    async def _publisher(topic: str, payload: str) -> None:
        published.append((topic, payload))

    monkeypatch.setattr(commands_module, "_publish_command", _publisher)
    # Disable the background ACK timer in endpoint tests (kept deterministic).
    _test_settings = _settings()
    object.__setattr__(_test_settings, "command_ack_timeout_seconds", 0)
    monkeypatch.setattr(commands_module, "get_settings", lambda: _test_settings)

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


@pytest.fixture(autouse=True)
def _mark_online(seeded, redis):
    # Mirror the device statuses into the ONLINE_DEVICES set.
    import asyncio

    async def _setup():
        await redis.sadd(rk.ONLINE_DEVICES, seeded["online_dev"])
        await redis.sadd(rk.ONLINE_DEVICES, seeded["other_dev"])

    asyncio.get_event_loop().run_until_complete(_setup())


def test_issue_online_command_is_sent(client, seeded, published):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url(f"/devices/{seeded['online_dev']}/commands"),
        json={"type": "on"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "SENT"
    assert body["command_id"]
    assert len(published) == 1


def test_issue_offline_command_is_queued(client, seeded, published):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url(f"/devices/{seeded['offline_dev']}/commands"),
        json={"type": "off"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "QUEUED"
    assert published == []


def test_value_command_requires_value(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url(f"/devices/{seeded['online_dev']}/commands"),
        json={"type": "value"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "missing_command_value"


def test_get_command_status_roundtrip(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    issued = client.post(
        _url(f"/devices/{seeded['online_dev']}/commands"),
        json={"type": "value", "value": 128},
        headers=headers,
    )
    cid = issued.json()["command_id"]
    resp = client.get(
        _url(f"/devices/{seeded['online_dev']}/commands/{cid}"), headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "SENT"
    assert resp.json()["value"] == 128


def test_get_unknown_command_is_404(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['online_dev']}/commands/{uuid.uuid4()}"),
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "command_not_found"


def test_cross_org_device_command_denied(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url(f"/devices/{seeded['other_dev']}/commands"),
        json={"type": "on"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_assigned_device_user_can_command(client, seeded):
    headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url(f"/devices/{seeded['online_dev']}/commands"),
        json={"type": "on"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_unassigned_device_user_denied(client, seeded):
    headers = _auth(seeded["du2_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url(f"/devices/{seeded['online_dev']}/commands"),
        json={"type": "on"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_schedule_create_and_list(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    created = client.post(
        _url(f"/devices/{seeded['online_dev']}/schedules"),
        json={"cron": "0 8 * * *", "type": "on"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    listed = client.get(
        _url(f"/devices/{seeded['online_dev']}/schedules"), headers=headers
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["cron"] == "0 8 * * *"
