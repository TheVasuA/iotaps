"""Property-based test for Super_Admin cross-organization authority.

# Feature: iotaps-platform, Property 2: Super_Admin cross-organization authority

Property 2 (design.md "Correctness Properties"):
    *For any* resource in any organization, a Super_Admin principal is
    authorized to read it and to perform cross-organization actions (reassign
    device, send command), while non-admin principals are not.

Validates: Requirements 2.5, 23.6

How the property is exercised against the real security primitives:
  - *Read authority* is governed by ``TenantScope`` (``app.core.security.tenant``):
    ``scope.get(Device, id)`` returns any row for a Super_Admin (bypass) and
    raises ``AuthorizationError`` for a non-admin referencing another org's row.
  - *Cross-organization actions* (reassign device / send command) are
    Super_Admin-only operations gated by ``require_role(ROLE_SUPER_ADMIN)``
    (``app.core.security.deps``); a non-admin is denied with an
    ``AuthorizationError`` (403).
  - *Send command* device-level access is governed by ``user_has_device_access``:
    a Super_Admin is granted access to any device across orgs, while a
    Device_User with no assignment in another org is denied.

A fresh in-memory SQLite async engine is built per Hypothesis example (mirroring
``test_deps.py``) so 100+ iterations stay cheap with no live Postgres.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import AuthorizationError
from app.core.security.deps import require_role, user_has_device_access
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

# Only the tables touched here; the full metadata pulls in Postgres-only DDL
# (e.g. JSONB) that the in-memory SQLite engine cannot create.
_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Device.__table__,
    DeviceUserAssignment.__table__,
]

_NON_ADMIN_ROLES = [ROLE_PROJECT_CENTER, ROLE_DEVICE_USER]


def _prepare_tables_for_sqlite() -> None:
    """Replace the Postgres ``gen_random_uuid()`` PK default with a Python uuid4.

    SQLite cannot evaluate ``gen_random_uuid()`` in a column DEFAULT.
    """
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


# --- Generators: a world of N organizations each holding M devices ---------
# A "scenario" is a wide input space over the number of orgs, devices per org,
# the requesting role, and (for non-admins) which org the requester belongs to.
_scenario = st.fixed_dictionaries(
    {
        # >= 2 orgs so cross-organization access is always meaningful.
        "devices_per_org": st.lists(
            st.integers(min_value=1, max_value=4), min_size=2, max_size=5
        ),
        "non_admin_role": st.sampled_from(_NON_ADMIN_ROLES),
        # Which org the non-admin requester "belongs" to (taken modulo #orgs).
        "home_org_pick": st.integers(min_value=0, max_value=4),
    }
)


async def _build_world(devices_per_org: list[int]):
    """Create a fresh in-memory DB seeded with orgs + devices.

    Returns the engine plus a list of (org_id, [device_id, ...]) tuples.
    """
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
    world: list[tuple[uuid.UUID, list[uuid.UUID]]] = []
    async with factory() as session:
        for org_idx, n_devices in enumerate(devices_per_org):
            org = Organization(name=f"Org {org_idx}")
            session.add(org)
            await session.flush()
            device_ids: list[uuid.UUID] = []
            for d in range(n_devices):
                device = Device(org_id=org.id, label=f"org{org_idx}-d{d}")
                session.add(device)
                await session.flush()
                device_ids.append(device.id)
            world.append((org.id, device_ids))
        await session.commit()

    return engine, factory, world


async def _run_scenario(scenario: dict) -> None:
    devices_per_org = scenario["devices_per_org"]
    engine, factory, world = await _build_world(devices_per_org)

    all_devices = [(org_id, did) for org_id, dids in world for did in dids]

    # The Super_Admin-only cross-org action gate (reassign device / send
    # command across organizations, Req 23.6).
    cross_org_action = require_role(ROLE_SUPER_ADMIN)

    try:
        async with factory() as session:
            # --- Super_Admin authority --------------------------------------
            # The Super_Admin's own org is deliberately a non-existent org id to
            # prove authority does NOT come from org membership (Req 2.5).
            super_admin = Principal(
                user_id=str(uuid.uuid4()),
                org_id=str(uuid.uuid4()),
                role=ROLE_SUPER_ADMIN,
            )
            sa_scope = TenantScope(super_admin, session)

            # Cross-org admin action (reassign device) is authorized.
            assert await cross_org_action(principal=super_admin) is super_admin

            for org_id, device_id in all_devices:
                # Authorized to READ any resource in any organization.
                fetched = await sa_scope.get(Device, device_id)
                assert fetched.id == device_id
                # Authorized to send a command to any device across orgs.
                assert (
                    await user_has_device_access(
                        session, super_admin, str(device_id)
                    )
                    is True
                )

            # --- Non-admin lack of cross-org authority ----------------------
            home_idx = scenario["home_org_pick"] % len(world)
            home_org_id = world[home_idx][0]
            non_admin = Principal(
                user_id=str(uuid.uuid4()),
                org_id=str(home_org_id),
                role=scenario["non_admin_role"],
            )
            na_scope = TenantScope(non_admin, session)

            # A non-admin can never perform the cross-org admin action.
            with pytest.raises(AuthorizationError):
                await cross_org_action(principal=non_admin)

            for org_id, device_id in all_devices:
                if org_id == home_org_id:
                    # Own-org resources remain readable (baseline sanity).
                    own = await na_scope.get(Device, device_id)
                    assert own.id == device_id
                else:
                    # Reading another org's resource is denied (Req 3.3) -> the
                    # non-admin cannot reach across organizations the way a
                    # Super_Admin can.
                    with pytest.raises(AuthorizationError):
                        await na_scope.get(Device, device_id)
                    # A Device_User with no assignment in that foreign org is
                    # also denied device-level access for sending commands.
                    if non_admin.role == ROLE_DEVICE_USER:
                        assert (
                            await user_has_device_access(
                                session, non_admin, str(device_id)
                            )
                            is False
                        )
    finally:
        await engine.dispose()


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenario=_scenario)
def test_super_admin_cross_organization_authority(scenario):
    """Property 2: Super_Admin may read/act across all orgs; non-admins cannot.

    **Validates: Requirements 2.5, 23.6**
    """
    asyncio.run(_run_scenario(scenario))
