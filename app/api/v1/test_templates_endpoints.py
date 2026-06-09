"""Endpoint tests for the Templates catalog and application (Task 11.1, Req 11).

Exercises the FastAPI templates router, ``POST /rules/from-template``, and
``POST /devices/{id}/apply-template`` end to end against an in-memory SQLite DB
(via a dependency override). Verifies catalog listing/filtering, that applying a
template configures the device's dashboard + rules from the definition, and that
rule-from-template instantiation works. Also covers the 9 seeded templates. No
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
from app.models.device import Device, DeviceGroup, MqttCredential
from app.models.infra import MqttNode, Template
from app.models.organization import Organization
from app.models.rule import Rule, RuleEdge, RuleNode
from app.models.user import User
from app.services.template_seeds import TEMPLATE_SEEDS, seed_templates

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    User.__table__,
    MqttNode.__table__,
    DeviceGroup.__table__,
    Device.__table__,
    MqttCredential.__table__,
    Template.__table__,
    Dashboard.__table__,
    Widget.__table__,
    Rule.__table__,
    RuleNode.__table__,
    RuleEdge.__table__,
]

# JSONB columns that need to become plain JSON on SQLite.
_JSON_COLUMNS = [
    (Template.__table__, "dashboard_def"),
    (Template.__table__, "rules_def"),
    (Dashboard.__table__, "layout"),
    (Widget.__table__, "config"),
    (Widget.__table__, "layout"),
    (Widget.__table__, "annotations"),
    (RuleNode.__table__, "config"),
    (RuleNode.__table__, "position"),
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    for table, column in _JSON_COLUMNS:
        table.c[column].type = JSON()
    # Postgres server defaults -> python-side defaults for SQLite.
    Rule.__table__.c.enabled.server_default = None
    Rule.__table__.c.enabled.default = ColumnDefault(True)
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


async def _seed_org(session_factory, plan: str | None) -> dict[str, str]:
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
        device = Device(org_id=org.id, label="dev-1")
        s.add_all([pc, du, device])
        await s.commit()
        return {
            "org_id": str(org.id),
            "pc_id": str(pc.id),
            "du_id": str(du.id),
            "device_id": str(device.id),
        }


@pytest.fixture()
async def seeded_catalog(session_factory) -> int:
    """Seed the 9-template catalog and return the number inserted."""
    async with session_factory() as s:
        return await seed_templates(s)


@pytest.fixture()
async def template_ids(session_factory) -> dict[str, str]:
    """Seed the catalog and return a {name: id} map."""
    from sqlalchemy import select

    async with session_factory() as s:
        await seed_templates(s)
        result = await s.execute(select(Template.id, Template.name))
        return {name: str(tid) for tid, name in result.all()}


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
async def free_org(session_factory):
    return await _seed_org(session_factory, "free")


@pytest.fixture()
async def pro_org(session_factory):
    return await _seed_org(session_factory, "pro")


# ---------------------------------------------------------------------------
# Seed catalog
# ---------------------------------------------------------------------------
def test_seed_inserts_nine_templates(seeded_catalog):
    assert seeded_catalog == 9
    assert len(TEMPLATE_SEEDS) == 9


async def test_seed_is_idempotent(session_factory):
    async with session_factory() as s:
        first = await seed_templates(s)
    async with session_factory() as s:
        second = await seed_templates(s)
    assert first == 9
    assert second == 0


# ---------------------------------------------------------------------------
# Catalog listing (Req 11.1, 11.2, 11.3)
# ---------------------------------------------------------------------------
def test_list_templates_returns_all_with_code_and_diagram(
    client, template_ids, free_org
):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(_url("/templates"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 9
    for t in body:
        assert t["arduino_code"]
        assert t["wiring_diagram_url"]
    names = {t["name"] for t in body}
    assert {"Temperature Monitor", "Water Level", "Soil Moisture", "Energy Meter"} <= names
    assert {
        "Water Tank",
        "Pump Control",
        "Cold Storage",
        "Smart Agriculture",
        "Industrial Motor",
    } <= names


def test_list_templates_filtered_by_category(client, template_ids, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    students = client.get(_url("/templates?category=student"), headers=headers).json()
    companies = client.get(_url("/templates?category=company"), headers=headers).json()
    assert {t["category"] for t in students} == {"student"}
    assert {t["category"] for t in companies} == {"company"}
    assert len(students) == 4
    assert len(companies) == 5


def test_list_templates_rejects_unknown_category(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    resp = client.get(_url("/templates?category=bogus"), headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_template_category"


def test_device_user_can_browse_catalog(client, template_ids, free_org):
    headers = _auth(free_org["du_id"], free_org["org_id"], ROLE_DEVICE_USER)
    resp = client.get(_url("/templates"), headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 9


# ---------------------------------------------------------------------------
# Apply template to device (Req 11.4)
# ---------------------------------------------------------------------------
def test_apply_template_configures_dashboard_and_rules(
    client, template_ids, pro_org
):
    tmpl_id = template_ids["Smart Agriculture"]
    headers = _auth(pro_org["pc_id"], pro_org["org_id"], ROLE_PROJECT_CENTER)

    resp = client.post(
        _url(f"/devices/{pro_org['device_id']}/apply-template"),
        json={"template_id": tmpl_id},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["device"]["template_id"] == tmpl_id

    # Dashboard created from the definition.
    dashboards = client.get(_url("/dashboards"), headers=headers).json()
    assert any(d["name"] == "Smart Agriculture" for d in dashboards)
    dash = next(d for d in dashboards if d["name"] == "Smart Agriculture")
    detail = client.get(_url(f"/dashboards/{dash['id']}"), headers=headers).json()
    assert len(detail["widgets"]) == 4

    # Rule created from the definition.
    rules = client.get(_url("/rules"), headers=headers).json()
    assert any(r["name"] == "Auto-irrigation on dry soil" for r in rules)


def test_apply_template_respects_free_plan_rule_limit(
    client, template_ids, free_org
):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)

    # Pre-fill the free org with 2 active rules.
    for name in ("r1", "r2"):
        client.post(
            _url("/rules"),
            json={"name": name, "enabled": True, "nodes": [], "edges": []},
            headers=headers,
        )
    tmpl_id = template_ids["Temperature Monitor"]
    resp = client.post(
        _url(f"/devices/{free_org['device_id']}/apply-template"),
        json={"template_id": tmpl_id},
        headers=headers,
    )
    # The template's rule would be the 3rd active rule -> blocked.
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "plan_limit_exceeded"


# ---------------------------------------------------------------------------
# Rule from template (Req 10.5)
# ---------------------------------------------------------------------------
def test_create_rule_from_template(client, template_ids, pro_org):
    tmpl_id = template_ids["Cold Storage"]
    headers = _auth(pro_org["pc_id"], pro_org["org_id"], ROLE_PROJECT_CENTER)

    resp = client.post(
        _url("/rules/from-template"),
        json={"template_id": tmpl_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    rule = resp.json()["rule"]
    assert rule["name"] == "Temperature excursion alert"
    assert rule["template_id"] == tmpl_id

    detail = client.get(_url(f"/rules/{rule['id']}"), headers=headers).json()
    assert len(detail["nodes"]) == 4  # trigger, condition, delay, action
    assert len(detail["edges"]) == 3
