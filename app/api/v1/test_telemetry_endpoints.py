"""Endpoint tests for the Telemetry query API (Task 5.7, Req 6.6).

Exercises ``GET /devices/{id}/telemetry`` and ``.../telemetry/latest`` end to
end against an in-memory SQLite DB. SQLite cannot host TimescaleDB continuous
aggregates, so the 5m/1h/1d rollup relations are emulated as plain tables with
the same ``(device_id, org_id, bucket, data)`` shape the service queries; the
raw ``telemetry`` table uses a ``ts`` column. This verifies resolution routing,
time-range filtering, ordering, tenant isolation, and Device_User access
scoping without a live Postgres/TimescaleDB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    Table,
    Uuid,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.config import Settings
from app.core.security import jwt as jwt_service
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

# Telemetry relations are not ORM-mapped for querying; define lightweight
# Core tables mirroring the raw hypertable + rollup views for the test DB.
_telemetry_meta = MetaData()


def _telemetry_table(name: str, time_col: str) -> Table:
    return Table(
        name,
        _telemetry_meta,
        Column("device_id", Uuid(), nullable=False),
        Column("org_id", Uuid(), nullable=False),
        Column(time_col, DateTime(timezone=True), nullable=False),
        Column("data", JSON, nullable=False),
    )


_raw = _telemetry_table("telemetry", "ts")
_t5m = _telemetry_table("telemetry_5m", "bucket")
_t1h = _telemetry_table("telemetry_1h", "bucket")
_t1d = _telemetry_table("telemetry_1d", "bucket")

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
    # SQLite can't render JSONB; swap the activity_logs detail column to JSON.
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
        await conn.run_sync(_telemetry_meta.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory):
    """Seed two orgs, a device in each, a Device_User, and telemetry rows."""
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        other = Organization(name="Other", type="project_center", plan="free")
        s.add_all([org, other])
        await s.flush()

        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        du = User(org_id=org.id, email="du@example.com", role=ROLE_DEVICE_USER)
        du2 = User(org_id=org.id, email="du2@example.com", role=ROLE_DEVICE_USER)
        node = MqttNode(
            ip="127.0.0.1", port=1883, capacity=100,
            active_connections=0, status="active",
        )
        device = Device(org_id=org.id, device_uid="dev-1", status="online")
        other_device = Device(org_id=other.id, device_uid="dev-2", status="online")
        s.add_all([pc, du, du2, node, device, other_device])
        await s.flush()

        # Assign the device to du only (du2 is unassigned).
        s.add(
            DeviceUserAssignment(org_id=org.id, device_id=device.id, user_id=du.id)
        )

        # Raw telemetry: 3 points one minute apart.
        for i, temp in enumerate((10.0, 11.0, 12.0)):
            await s.execute(
                _raw.insert().values(
                    device_id=device.id,
                    org_id=org.id,
                    ts=base + timedelta(minutes=i),
                    data={"temp": temp},
                )
            )
        # A 5m rollup bucket.
        await s.execute(
            _t5m.insert().values(
                device_id=device.id,
                org_id=org.id,
                bucket=base,
                data={"temp": 11.0},
            )
        )
        # Telemetry belonging to the OTHER org's device (must never leak).
        await s.execute(
            _raw.insert().values(
                device_id=other_device.id,
                org_id=other.id,
                ts=base,
                data={"temp": 99.0},
            )
        )
        await s.commit()
        return {
            "org_id": str(org.id),
            "other_org_id": str(other.id),
            "pc_id": str(pc.id),
            "du_id": str(du.id),
            "du2_id": str(du2.id),
            "device_id": str(device.id),
            "other_device_id": str(other_device.id),
            "base": base,
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


def test_get_raw_telemetry_ordered_oldest_first(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry"), headers=headers
    )
    assert resp.status_code == 200, resp.text
    points = resp.json()
    assert [p["data"]["temp"] for p in points] == [10.0, 11.0, 12.0]


def test_resolution_selects_rollup_view(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry?resolution=5m"),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    points = resp.json()
    assert len(points) == 1
    assert points[0]["data"]["temp"] == 11.0


def test_invalid_resolution_is_rejected(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry?resolution=bogus"),
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_resolution"


def test_time_range_filters_points(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    base = seeded["base"]
    start = (base + timedelta(minutes=1)).isoformat()
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry"),
        params={"from": start},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    points = resp.json()
    assert [p["data"]["temp"] for p in points] == [11.0, 12.0]


def test_latest_returns_most_recent_point(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry/latest"), headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["temp"] == 12.0


def test_latest_404_when_no_telemetry(client, seeded):
    # other_device has telemetry under other org; query it as that org but with
    # a fresh device that has none -> create scenario via a device with no rows.
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    # Provision a new device with no telemetry.
    created = client.post(_url("/devices"), json={"label": "Empty"}, headers=headers)
    new_id = created.json()["device"]["id"]
    resp = client.get(
        _url(f"/devices/{new_id}/telemetry/latest"), headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "telemetry_not_found"


def test_cross_org_device_is_denied(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(
        _url(f"/devices/{seeded['other_device_id']}/telemetry"), headers=headers
    )
    assert resp.status_code == 403


def test_assigned_device_user_can_read(client, seeded):
    headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry"), headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 3


def test_unassigned_device_user_is_denied(client, seeded):
    headers = _auth(seeded["du2_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.get(
        _url(f"/devices/{seeded['device_id']}/telemetry"), headers=headers
    )
    assert resp.status_code == 403
