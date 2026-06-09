"""Property-based test for tenant isolation and access scope (Task 2.6).

# Feature: iotaps-platform, Property 1: Tenant isolation and access scope

Property 1 (design.md "Correctness Properties"):

    For any set of organizations each holding random devices, dashboards,
    rules, and billing records, and for any requesting user, every list/read
    query returns only resources whose ``org_id`` equals the requester's
    ``org_id``, and any direct reference to a resource owned by a different
    ``org_id`` is denied with an authorization error. For any Device_User, the
    set of accessible devices equals exactly the set of devices assigned to
    that user (a subset of the user's org).

Validates: Requirements 2.4, 3.2, 3.3

The DB-touching paths use an in-memory SQLite async engine (aiosqlite), mirroring
``test_deps.py``: only the handful of models involved are created, and the
Postgres ``gen_random_uuid()`` PK default is swapped for a Python ``uuid4`` since
SQLite cannot evaluate it in a column DEFAULT.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import AuthorizationError
from app.core.security.deps import user_has_device_access
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.db.base import Base
from app.models.billing import Subscription
from app.models.dashboard import Dashboard
from app.models.device import Device, DeviceUserAssignment
from app.models.organization import Organization
from app.models.rule import Rule
from app.models.user import User

# Only these tables are needed; creating the full metadata would pull in
# Postgres-specific DDL (JSONB) unsupported by the in-memory SQLite engine.
_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Device.__table__,
    DeviceUserAssignment.__table__,
    Dashboard.__table__,
    Rule.__table__,
    Subscription.__table__,
]

# The tenant-scoped resource models exercised by the list/read property.
_RESOURCE_MODELS = (Device, Dashboard, Rule, Subscription)


def _prepare_tables_for_sqlite() -> None:
    """Swap the Postgres ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    """Render Postgres ``JSONB`` columns as SQLite ``JSON`` for the test engine.

    The Dashboard model carries a ``JSONB`` ``layout`` column which SQLite can't
    compile natively; mapping it to ``JSON`` lets ``create_all`` succeed without
    altering production DDL.
    """
    return "JSON"


_prepare_tables_for_sqlite()


# ---------------------------------------------------------------------------
# Generators: constrain to the input space intelligently.
# ---------------------------------------------------------------------------
# An org's holdings: small non-negative counts of each resource type.
_count = st.integers(min_value=0, max_value=3)

_org_spec = st.fixed_dictionaries(
    {
        "n_devices": _count,
        "n_dashboards": _count,
        "n_rules": _count,
        "n_subs": _count,
    }
)


@st.composite
def _scenario(draw: st.DrawFn) -> dict:
    """A set of organizations with random holdings + a requesting user.

    Also includes a per-requester-org-device assignment mask used to drive the
    Device_User access-scope check.
    """
    org_specs = draw(st.lists(_org_spec, min_size=1, max_size=4))
    n_orgs = len(org_specs)
    requester_idx = draw(st.integers(min_value=0, max_value=n_orgs - 1))
    # Assignment mask for the requester-org's devices (length == that org's
    # device count); each flag decides whether the Device_User is assigned.
    n_req_devices = org_specs[requester_idx]["n_devices"]
    assign_mask = draw(
        st.lists(st.booleans(), min_size=n_req_devices, max_size=n_req_devices)
    )
    return {
        "org_specs": org_specs,
        "requester_idx": requester_idx,
        "assign_mask": assign_mask,
    }


# ---------------------------------------------------------------------------
# Async harness: build a fresh in-memory DB per example, seed, and assert.
# ---------------------------------------------------------------------------
async def _seed(session: AsyncSession, org_specs: list[dict]) -> list[dict]:
    """Create orgs and their holdings; return per-org id bookkeeping."""
    orgs: list[dict] = []
    for i, spec in enumerate(org_specs):
        org = Organization(name=f"Org {i}")
        session.add(org)
        await session.flush()

        device_ids: list[uuid.UUID] = []
        for d in range(spec["n_devices"]):
            device = Device(org_id=org.id, label=f"dev-{i}-{d}")
            session.add(device)
            await session.flush()
            device_ids.append(device.id)

        resource_ids: dict[type, list[uuid.UUID]] = {Device: list(device_ids)}

        dash_ids = []
        for k in range(spec["n_dashboards"]):
            row = Dashboard(org_id=org.id, name=f"dash-{i}-{k}")
            session.add(row)
            await session.flush()
            dash_ids.append(row.id)
        resource_ids[Dashboard] = dash_ids

        rule_ids = []
        for k in range(spec["n_rules"]):
            row = Rule(org_id=org.id, name=f"rule-{i}-{k}")
            session.add(row)
            await session.flush()
            rule_ids.append(row.id)
        resource_ids[Rule] = rule_ids

        sub_ids = []
        for k in range(spec["n_subs"]):
            row = Subscription(org_id=org.id, plan="free")
            session.add(row)
            await session.flush()
            sub_ids.append(row.id)
        resource_ids[Subscription] = sub_ids

        orgs.append({"org_id": org.id, "resource_ids": resource_ids})

    await session.commit()
    return orgs


async def _run(scenario: dict) -> None:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES)
            )
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            orgs = await _seed(session, scenario["org_specs"])

            req_idx = scenario["requester_idx"]
            req_org_id = orgs[req_idx]["org_id"]
            principal = Principal(
                user_id="requester",
                org_id=str(req_org_id),
                role=ROLE_PROJECT_CENTER,
            )
            scope = TenantScope(principal, session)

            # ---- list/read queries return only the requester's org (Req 3.2)
            for model in _RESOURCE_MODELS:
                rows = (await session.execute(scope.select(model))).scalars().all()
                returned_ids = {r.id for r in rows}
                expected_ids = set(orgs[req_idx]["resource_ids"][model])
                assert returned_ids == expected_ids, (
                    f"{model.__name__}: leaked or missing rows; "
                    f"expected {expected_ids}, got {returned_ids}"
                )
                # Every returned row truly belongs to the requester's org.
                assert all(str(r.org_id) == str(req_org_id) for r in rows)

            # ---- direct reference to a foreign-org resource is denied (Req 3.3)
            for other_idx, other in enumerate(orgs):
                if other_idx == req_idx:
                    continue
                for model in _RESOURCE_MODELS:
                    for rid in other["resource_ids"][model]:
                        with pytest.raises(AuthorizationError):
                            await scope.get(model, rid)

            # ---- own-org references resolve successfully (Req 3.3 converse)
            for model in _RESOURCE_MODELS:
                for rid in orgs[req_idx]["resource_ids"][model]:
                    fetched = await scope.get(model, rid)
                    assert fetched.id == rid

            # ---- Device_User accessible devices == assigned devices (Req 2.4)
            req_device_ids = orgs[req_idx]["resource_ids"][Device]
            mask = scenario["assign_mask"]
            assigned: set[uuid.UUID] = set()

            du = User(org_id=req_org_id, email="du@example.com", role=ROLE_DEVICE_USER)
            session.add(du)
            await session.flush()

            for device_id, flag in zip(req_device_ids, mask):
                if flag:
                    session.add(
                        DeviceUserAssignment(
                            org_id=req_org_id, device_id=device_id, user_id=du.id
                        )
                    )
                    assigned.add(device_id)
            await session.commit()

            du_principal = Principal(
                user_id=str(du.id), org_id=str(req_org_id), role=ROLE_DEVICE_USER
            )

            # Accessible set equals exactly the assigned set across every device
            # in the platform (assigned -> allowed, everything else -> denied).
            all_device_ids = [
                did for o in orgs for did in o["resource_ids"][Device]
            ]
            for device_id in all_device_ids:
                allowed = await user_has_device_access(
                    session, du_principal, str(device_id)
                )
                assert allowed is (device_id in assigned), (
                    f"device {device_id}: access={allowed} "
                    f"but assigned={device_id in assigned}"
                )
    finally:
        await engine.dispose()


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenario=_scenario())
def test_tenant_isolation_and_access_scope(scenario: dict) -> None:
    """Property 1: tenant isolation, cross-org denial, and Device_User scope.

    Validates: Requirements 2.4, 3.2, 3.3
    """
    asyncio.run(_run(scenario))
