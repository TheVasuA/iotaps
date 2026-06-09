"""Endpoint tests for the Support Chat API (Task 19.4, Req 21).

Exercises the FastAPI support router end to end against an in-memory SQLite DB
(via a dependency override). Verifies:

- A Device_User's message is delivered to the Project_Center that owns the
  assigned device, with the device identity attached (Req 21.1, 21.2).
- A Project_Center reply is routed back to the originating Device_User (Req 21.3).
- A Device_User may only message a device assigned to them (Req 2.4) and only
  reads their own conversation; RBAC keeps roles to their permitted actions.

No live Postgres/Redis/MQTT is required.
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

import app.models  # noqa: F401  (register all models on Base.metadata)
from app.core.config import Settings
from app.core.security import jwt as jwt_service
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
)
from app.db.base import Base
from app.db.session import get_session
from app.main import API_V1_PREFIX, create_app
from app.models.device import Device, DeviceUserAssignment
from app.models.ops import SupportChat
from app.models.organization import Organization
from app.models.user import User

_TABLES = [
    Organization.__table__,
    User.__table__,
    Device.__table__,
    DeviceUserAssignment.__table__,
    SupportChat.__table__,
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
    """Seed one Project_Center org with a device assigned to a Device_User.

    Also seeds a second org with its own Project_Center + Device_User + device to
    assert cross-tenant isolation.
    """
    async with session_factory() as s:
        org = Organization(name="PC", type="project_center", plan="pro")
        other = Organization(name="OtherPC", type="project_center", plan="pro")
        s.add_all([org, other])
        await s.flush()

        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        du = User(org_id=org.id, email="du@example.com", role=ROLE_DEVICE_USER)
        du2 = User(org_id=org.id, email="du2@example.com", role=ROLE_DEVICE_USER)
        other_pc = User(
            org_id=other.id, email="opc@example.com", role=ROLE_PROJECT_CENTER
        )
        s.add_all([pc, du, du2, other_pc])
        await s.flush()

        device = Device(org_id=org.id, device_uid="dev-1", label="Pump")
        s.add(device)
        await s.flush()

        # Assign the device to du (but not du2).
        s.add(
            DeviceUserAssignment(
                org_id=org.id, device_id=device.id, user_id=du.id
            )
        )
        await s.commit()
        return {
            "org_id": str(org.id),
            "other_org_id": str(other.id),
            "pc_id": str(pc.id),
            "du_id": str(du.id),
            "du2_id": str(du2.id),
            "other_pc_id": str(other_pc.id),
            "device_id": str(device.id),
        }


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


def test_support_requires_auth(client):
    assert client.get(_url("/support/messages")).status_code == 401


def test_user_message_delivered_to_project_center_with_device_identity(client, seeded):
    """Device_User message reaches the device's Project_Center w/ device id (Req 21.1, 21.2)."""
    du_headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "My pump is offline"},
        headers=du_headers,
    )
    assert resp.status_code == 201, resp.text
    msg = resp.json()["message"]
    assert msg["device_id"] == seeded["device_id"]  # device identity (21.2)
    assert msg["device_user_id"] == seeded["du_id"]
    assert msg["project_center_id"] == seeded["org_id"]  # delivered to PC (21.1)
    assert msg["sender_role"] == "device_user"

    # The Project_Center sees the message in its organization (Req 21.1).
    pc_headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    listed = client.get(_url("/support/messages"), headers=pc_headers)
    assert listed.status_code == 200
    ids = [m["id"] for m in listed.json()]
    assert msg["id"] in ids


def test_project_center_reply_routed_to_originating_user(client, seeded):
    """A PC reply is routed back to the originating Device_User (Req 21.3)."""
    du_headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    sent = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "Need help"},
        headers=du_headers,
    ).json()["message"]

    pc_headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    reply = client.post(
        _url(f"/support/messages/{sent['id']}/reply"),
        json={"message": "We are looking into it"},
        headers=pc_headers,
    )
    assert reply.status_code == 201, reply.text
    reply_msg = reply.json()["message"]
    assert reply_msg["sender_role"] == "project_center"
    # Routed to the originating Device_User (Req 21.3).
    assert reply_msg["device_user_id"] == seeded["du_id"]
    assert reply_msg["device_id"] == seeded["device_id"]

    # The originating Device_User sees the reply in their conversation.
    listed = client.get(_url("/support/messages"), headers=du_headers).json()
    assert any(m["id"] == reply_msg["id"] for m in listed)


def test_device_user_cannot_message_unassigned_device(client, seeded):
    """A Device_User may only message a device assigned to them (Req 2.4)."""
    du2_headers = _auth(seeded["du2_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "hi"},
        headers=du2_headers,
    )
    assert resp.status_code == 403


def test_device_user_only_sees_own_conversation(client, seeded):
    """One Device_User must not read another's support thread (Req 21.3)."""
    du_headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "private"},
        headers=du_headers,
    )

    du2_headers = _auth(seeded["du2_id"], seeded["org_id"], ROLE_DEVICE_USER)
    listed = client.get(_url("/support/messages"), headers=du2_headers)
    assert listed.status_code == 200
    assert listed.json() == []  # du2 sees none of du's messages


def test_project_center_cannot_send_user_message(client, seeded):
    """RBAC: sending a Device_User message is restricted to Device_User (Req 2.2/2.3)."""
    pc_headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "x"},
        headers=pc_headers,
    )
    assert resp.status_code == 403


def test_device_user_cannot_reply(client, seeded):
    """RBAC: replying is restricted to Project_Center (Req 2.2/2.3)."""
    du_headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    sent = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "hi"},
        headers=du_headers,
    ).json()["message"]
    resp = client.post(
        _url(f"/support/messages/{sent['id']}/reply"),
        json={"message": "self reply"},
        headers=du_headers,
    )
    assert resp.status_code == 403


def test_other_org_project_center_cannot_reply(client, seeded):
    """A PC in another org cannot reply to this org's message (Req 3.3)."""
    du_headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    sent = client.post(
        _url("/support/messages"),
        json={"device_id": seeded["device_id"], "message": "hi"},
        headers=du_headers,
    ).json()["message"]

    other_headers = _auth(
        seeded["other_pc_id"], seeded["other_org_id"], ROLE_PROJECT_CENTER
    )
    resp = client.post(
        _url(f"/support/messages/{sent['id']}/reply"),
        json={"message": "intercept"},
        headers=other_headers,
    )
    assert resp.status_code == 403
