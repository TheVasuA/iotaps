"""Unit tests for the middleware-stack dependencies (Task 2.5, Req 2 & 3).

Covers stages 2-4 of the design's middleware stack plus the Device_User
device-access restriction:
  - JWT verification -> Principal (Req 2.2), and rejection of missing/invalid
    bearer tokens (401)
  - require_role RBAC: permitted role passes, others denied with 403; Super_Admin
    always permitted (Req 2.2, 2.3, 2.5)
  - TenantScope.select filters by org_id, Super_Admin bypasses (Req 3.2, 2.5)
  - TenantScope.get denies cross-org access with 403 (Req 3.3)
  - Device_User access limited to assigned devices via device_user_assignments
    (Req 2.4)

The DB-touching paths use an in-memory SQLite async session so no live Postgres
is needed; only the few models involved are created.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.config import Settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import jwt as jwt_service
from app.core.security.deps import (
    _principal_from_authorization,
    require_role,
    user_has_device_access,
)
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.db.base import Base
from app.models.device import Device, DeviceUserAssignment
from app.models.organization import Organization
from app.models.user import User

# Only these tables are needed; creating the full metadata would pull in
# Postgres-specific DDL (JSONB) unsupported by the in-memory SQLite test engine.
_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Device.__table__,
    DeviceUserAssignment.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Swap the Postgres ``gen_random_uuid()`` PK default for a Python uuid4.

    SQLite cannot evaluate ``gen_random_uuid()`` in a column DEFAULT.
    """
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", jwt_algorithm="HS256")


def _bearer(role: str, *, org_id: str = "o1", user_id: str = "u1") -> str:
    token = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=_settings()
    )
    return f"Bearer {token}"


# ---------------------------------------------------------------------------
# Stage 2: JWT verification -> principal
# ---------------------------------------------------------------------------
def test_principal_from_valid_bearer(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings)
    principal = _principal_from_authorization(_bearer(ROLE_PROJECT_CENTER))
    assert principal.user_id == "u1"
    assert principal.org_id == "o1"
    assert principal.role == ROLE_PROJECT_CENTER


def test_principal_missing_token_raises_401():
    with pytest.raises(AuthenticationError):
        _principal_from_authorization(None)
    with pytest.raises(AuthenticationError):
        _principal_from_authorization("Token abc")


def test_principal_invalid_token_raises_401(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings)
    with pytest.raises(AuthenticationError):
        _principal_from_authorization("Bearer not-a-jwt")


# ---------------------------------------------------------------------------
# Stage 3: RBAC require_role
# ---------------------------------------------------------------------------
async def test_require_role_permits_allowed_role():
    checker = require_role(ROLE_PROJECT_CENTER)
    principal = Principal(user_id="u1", org_id="o1", role=ROLE_PROJECT_CENTER)
    assert await checker(principal=principal) is principal


async def test_require_role_denies_disallowed_role():
    checker = require_role(ROLE_PROJECT_CENTER)
    principal = Principal(user_id="u1", org_id="o1", role=ROLE_DEVICE_USER)
    with pytest.raises(AuthorizationError):
        await checker(principal=principal)


async def test_require_role_super_admin_always_permitted():
    checker = require_role(ROLE_PROJECT_CENTER)  # SA not even listed
    principal = Principal(user_id="u1", org_id="o1", role=ROLE_SUPER_ADMIN)
    assert await checker(principal=principal) is principal


# ---------------------------------------------------------------------------
# In-memory DB fixture for tenant/device tests
# ---------------------------------------------------------------------------
@pytest.fixture
async def session() -> AsyncSession:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_org_device(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    org = Organization(name="Org A")
    session.add(org)
    await session.flush()
    device = Device(org_id=org.id, label="d1")
    session.add(device)
    await session.flush()
    return org.id, device.id


# ---------------------------------------------------------------------------
# Stage 4: TenantScope filtering and cross-org denial
# ---------------------------------------------------------------------------
async def test_tenant_scope_select_filters_by_org(session):
    org_id, device_id = await _seed_org_device(session)
    principal = Principal(user_id="u1", org_id=str(org_id), role=ROLE_PROJECT_CENTER)
    scope = TenantScope(principal, session)

    rows = (await session.execute(scope.select(Device))).scalars().all()
    assert [d.id for d in rows] == [device_id]

    # A different org sees nothing.
    other = Principal(user_id="u2", org_id=str(uuid.uuid4()), role=ROLE_PROJECT_CENTER)
    other_scope = TenantScope(other, session)
    assert (await session.execute(other_scope.select(Device))).scalars().all() == []


async def test_tenant_scope_super_admin_bypasses_filter(session):
    org_id, device_id = await _seed_org_device(session)
    # Super_Admin's own org differs, yet still sees the device (Req 2.5).
    sa = Principal(user_id="admin", org_id=str(uuid.uuid4()), role=ROLE_SUPER_ADMIN)
    scope = TenantScope(sa, session)
    rows = (await session.execute(scope.select(Device))).scalars().all()
    assert device_id in [d.id for d in rows]


async def test_tenant_scope_get_denies_cross_org(session):
    org_id, device_id = await _seed_org_device(session)
    intruder = Principal(
        user_id="u2", org_id=str(uuid.uuid4()), role=ROLE_PROJECT_CENTER
    )
    scope = TenantScope(intruder, session)
    with pytest.raises(AuthorizationError):
        await scope.get(Device, device_id)


async def test_tenant_scope_get_allows_same_org(session):
    org_id, device_id = await _seed_org_device(session)
    owner = Principal(user_id="u1", org_id=str(org_id), role=ROLE_PROJECT_CENTER)
    scope = TenantScope(owner, session)
    fetched = await scope.get(Device, device_id)
    assert fetched.id == device_id


# ---------------------------------------------------------------------------
# Device_User access restriction (Req 2.4)
# ---------------------------------------------------------------------------
async def test_device_user_access_requires_assignment(session):
    org_id, device_id = await _seed_org_device(session)
    user = User(org_id=org_id, email="du@example.com", role=ROLE_DEVICE_USER)
    session.add(user)
    await session.flush()

    principal = Principal(
        user_id=str(user.id), org_id=str(org_id), role=ROLE_DEVICE_USER
    )
    # No assignment yet -> denied.
    assert await user_has_device_access(session, principal, str(device_id)) is False

    # Assign the device -> allowed.
    session.add(
        DeviceUserAssignment(org_id=org_id, device_id=device_id, user_id=user.id)
    )
    await session.flush()
    assert await user_has_device_access(session, principal, str(device_id)) is True


async def test_super_admin_and_project_center_device_access(session):
    org_id, device_id = await _seed_org_device(session)
    sa = Principal(user_id="a", org_id=str(uuid.uuid4()), role=ROLE_SUPER_ADMIN)
    pc = Principal(user_id="b", org_id=str(org_id), role=ROLE_PROJECT_CENTER)
    assert await user_has_device_access(session, sa, str(device_id)) is True
    # Project_Center passes the device-access gate (tenant filter governs org).
    assert await user_has_device_access(session, pc, str(device_id)) is True
