"""Endpoint tests for the Rules API (Task 10.1, Req 10).

Exercises the FastAPI rules router end to end against an in-memory SQLite DB
(via a dependency override). Verifies graph persistence (nodes + edges), the
per-plan active-rule limit (Free/ambiguous = max 2, Pro = unlimited), RBAC, and
tenant scoping. No live Postgres/Redis/MQTT is required.
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
from app.models.organization import Organization
from app.models.rule import Rule, RuleEdge, RuleNode
from app.models.user import User

import app.models  # noqa: F401  (register all models on Base.metadata)

_TABLES = [
    Organization.__table__,
    User.__table__,
    Rule.__table__,
    RuleNode.__table__,
    RuleEdge.__table__,
]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    # JSONB -> JSON for SQLite-backed tests.
    RuleNode.__table__.c.config.type = JSON()
    RuleNode.__table__.c.position.type = JSON()
    # enabled has a Postgres server_default; give SQLite a python-side default.
    Rule.__table__.c.enabled.server_default = None
    Rule.__table__.c.enabled.default = ColumnDefault(True)


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


def _create_rule(client, headers, name: str, enabled: bool = True):
    return client.post(
        _url("/rules"),
        json={
            "name": name,
            "enabled": enabled,
            "nodes": [
                {"id": "n1", "node_type": "trigger", "config": {"metric": "temp"}},
                {"id": "n2", "node_type": "action", "config": {"cmd": "on"}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        },
        headers=headers,
    )


@pytest.fixture()
async def free_org(session_factory):
    return await _seed_org(session_factory, "free")


@pytest.fixture()
async def pro_org(session_factory):
    return await _seed_org(session_factory, "pro")


@pytest.fixture()
async def ambiguous_org(session_factory):
    return await _seed_org(session_factory, None)


def test_create_rule_persists_graph(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    resp = _create_rule(client, headers, "Temp alert")
    assert resp.status_code == 201, resp.text
    rule_id = resp.json()["rule"]["id"]

    detail = client.get(_url(f"/rules/{rule_id}"), headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["rule"]["name"] == "Temp alert"
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    # Edge wired to the persisted DB node ids.
    node_ids = {n["id"] for n in body["nodes"]}
    assert body["edges"][0]["from_node_id"] in node_ids
    assert body["edges"][0]["to_node_id"] in node_ids


def test_device_user_cannot_manage_rules(client, free_org):
    headers = _auth(free_org["du_id"], free_org["org_id"], ROLE_DEVICE_USER)
    resp = _create_rule(client, headers, "x")
    assert resp.status_code == 403


def test_free_plan_limited_to_two_active_rules(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    assert _create_rule(client, headers, "r1").status_code == 201
    assert _create_rule(client, headers, "r2").status_code == 201
    third = _create_rule(client, headers, "r3")
    assert third.status_code == 403
    assert third.json()["error_code"] == "plan_limit_exceeded"


def test_ambiguous_plan_uses_free_limit(client, ambiguous_org):
    headers = _auth(
        ambiguous_org["pc_id"], ambiguous_org["org_id"], ROLE_PROJECT_CENTER
    )
    assert _create_rule(client, headers, "r1").status_code == 201
    assert _create_rule(client, headers, "r2").status_code == 201
    assert _create_rule(client, headers, "r3").status_code == 403


def test_pro_plan_unlimited_active_rules(client, pro_org):
    headers = _auth(pro_org["pc_id"], pro_org["org_id"], ROLE_PROJECT_CENTER)
    for i in range(5):
        assert _create_rule(client, headers, f"r{i}").status_code == 201


def test_disabled_rules_do_not_count_toward_limit(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    assert _create_rule(client, headers, "r1").status_code == 201
    assert _create_rule(client, headers, "r2").status_code == 201
    # A disabled rule is allowed even at the active limit.
    assert _create_rule(client, headers, "r3", enabled=False).status_code == 201


def test_enabling_rule_rechecks_limit(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    assert _create_rule(client, headers, "r1").status_code == 201
    assert _create_rule(client, headers, "r2").status_code == 201
    disabled = _create_rule(client, headers, "r3", enabled=False)
    rule_id = disabled.json()["rule"]["id"]
    # Toggling it on would make 3 active -> blocked.
    resp = client.patch(
        _url(f"/rules/{rule_id}"), json={"enabled": True}, headers=headers
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "plan_limit_exceeded"


def test_disable_then_create_allows_new_active_rule(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    r1 = _create_rule(client, headers, "r1")
    assert _create_rule(client, headers, "r2").status_code == 201
    # Disable r1, freeing a slot.
    client.patch(
        _url(f"/rules/{r1.json()['rule']['id']}"),
        json={"enabled": False},
        headers=headers,
    )
    assert _create_rule(client, headers, "r3").status_code == 201


def test_update_replaces_graph(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    rule_id = _create_rule(client, headers, "r1").json()["rule"]["id"]
    resp = client.patch(
        _url(f"/rules/{rule_id}"),
        json={
            "nodes": [{"id": "a", "node_type": "trigger"}],
            "edges": [],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    detail = client.get(_url(f"/rules/{rule_id}"), headers=headers).json()
    assert len(detail["nodes"]) == 1
    assert len(detail["edges"]) == 0


def test_delete_rule(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    rule_id = _create_rule(client, headers, "r1").json()["rule"]["id"]
    assert client.delete(_url(f"/rules/{rule_id}"), headers=headers).status_code == 204
    assert client.get(_url(f"/rules/{rule_id}"), headers=headers).status_code == 403


@pytest.fixture()
async def second_org(session_factory):
    return await _seed_org(session_factory, "free")


def test_tenant_isolation_lists_only_own_rules(client, free_org, second_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    _create_rule(client, headers, "mine")
    other_headers = _auth(
        second_org["pc_id"], second_org["org_id"], ROLE_PROJECT_CENTER
    )
    _create_rule(client, other_headers, "theirs")

    mine = client.get(_url("/rules"), headers=headers).json()
    assert [r["name"] for r in mine] == ["mine"]


def test_invalid_edge_reference_rejected(client, free_org):
    headers = _auth(free_org["pc_id"], free_org["org_id"], ROLE_PROJECT_CENTER)
    resp = client.post(
        _url("/rules"),
        json={
            "name": "bad",
            "nodes": [{"id": "n1", "node_type": "trigger"}],
            "edges": [{"from": "n1", "to": "missing"}],
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "invalid_rule_graph"
