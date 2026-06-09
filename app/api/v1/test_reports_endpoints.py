"""Endpoint tests for the Reports API (Task 12.1, Req 14).

Exercises ``POST /reports`` (CSV/PDF generation), ``POST /reports/schedule``
(cron-driven scheduling), and ``GET /reports/{id}/download`` end to end against
an in-memory SQLite DB. As with the telemetry endpoint tests, the raw
``telemetry`` relation is emulated as a plain table with a ``ts`` column. Tenant
isolation and Device_User access scoping are verified alongside output content.
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
from app.models.ops import ActivityLog, ScheduledReport
from app.models.organization import Organization
from app.models.user import User

import app.models  # noqa: F401  (register all models on Base.metadata)

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

_TABLES = [
    Organization.__table__,
    User.__table__,
    MqttNode.__table__,
    DeviceGroup.__table__,
    Device.__table__,
    MqttCredential.__table__,
    DeviceUserAssignment.__table__,
    ActivityLog.__table__,
    ScheduledReport.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    # SQLite can't render JSONB; swap JSONB columns to JSON.
    ActivityLog.__table__.c.detail.type = JSON()
    ScheduledReport.__table__.c.query.type = JSON()


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
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        other = Organization(name="Other", type="project_center", plan="free")
        s.add_all([org, other])
        await s.flush()

        pc = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
        du = User(org_id=org.id, email="du@example.com", role=ROLE_DEVICE_USER)
        du2 = User(org_id=org.id, email="du2@example.com", role=ROLE_DEVICE_USER)
        device = Device(org_id=org.id, device_uid="dev-1", status="online")
        other_device = Device(org_id=other.id, device_uid="dev-2", status="online")
        s.add_all([pc, du, du2, device, other_device])
        await s.flush()

        s.add(
            DeviceUserAssignment(org_id=org.id, device_id=device.id, user_id=du.id)
        )

        for i, temp in enumerate((10.0, 11.0, 12.0)):
            await s.execute(
                _raw.insert().values(
                    device_id=device.id,
                    org_id=org.id,
                    ts=base + timedelta(minutes=i),
                    data={"temp": temp},
                )
            )
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


def test_generate_csv_report_and_download(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["device_id"]], "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["format"] == "csv"
    assert body["download_url"].endswith(f"/reports/{body['report_id']}/download")

    dl = client.get(
        _url(f"/reports/{body['report_id']}/download"), headers=headers
    )
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"].startswith("text/csv")
    text = dl.text
    assert "device_id,ts,temp" in text
    assert "10.0" in text and "12.0" in text
    # The other org's telemetry must never appear.
    assert "99.0" not in text


def test_generate_pdf_report(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["device_id"]], "format": "pdf"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    report_id = resp.json()["report_id"]
    dl = client.get(_url(f"/reports/{report_id}/download"), headers=headers)
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/pdf")
    assert dl.content.startswith(b"%PDF")


def test_generate_report_rejects_unknown_format(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["device_id"]], "format": "xlsx"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_report_format"


def test_generate_report_cross_org_device_denied(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["other_device_id"]], "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_unassigned_device_user_cannot_report(client, seeded):
    headers = _auth(seeded["du2_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["device_id"]], "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_assigned_device_user_can_report(client, seeded):
    headers = _auth(seeded["du_id"], seeded["org_id"], ROLE_DEVICE_USER)
    resp = client.post(
        _url("/reports"),
        json={"device_ids": [seeded["device_id"]], "format": "csv"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_schedule_report_persists_definition(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports/schedule"),
        json={
            "query": {"device_ids": [seeded["device_id"]], "format": "pdf"},
            "schedule_cron": "0 6 * * *",
            "destination": "ops@example.com",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    sr = resp.json()["scheduled_report"]
    assert sr["schedule_cron"] == "0 6 * * *"
    assert sr["destination"] == "ops@example.com"
    assert sr["format"] == "pdf"
    assert sr["query"]["device_ids"] == [seeded["device_id"]]


def test_schedule_report_requires_devices(client, seeded):
    headers = _auth(seeded["pc_id"], seeded["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/reports/schedule"),
        json={
            "query": {"device_ids": []},
            "schedule_cron": "0 6 * * *",
            "destination": "ops@example.com",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_report_query"
