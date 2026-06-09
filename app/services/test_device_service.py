"""Unit tests for the DeviceService (Task 4.1, Req 5).

Exercises device provisioning, credential generation/revocation, QR encoding,
label override, group association, user assignment, maintenance toggling, and
activity-log writes against an in-memory SQLite database. No live
Postgres/Redis/MQTT is required.

Covered acceptance criteria:
  - 5.1 provisioning creates a device under the org + unique MQTT credentials
  - 5.2 QR code encodes the device identity
  - 5.3 / 5.4 rename / custom label stored
  - 5.5 group association
  - 5.6 device assigned to a Device_User
  - 5.7 maintenance_mode toggle
  - 5.8 activity-log entries for provision/assign/rename/config/delete
  - 5.9 deletion removes the device and revokes its MQTT credentials
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.security import password as password_service
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.db.base import Base
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
from app.services.device_service import (
    ACTION_ASSIGN,
    ACTION_COMMAND,
    ACTION_CONFIG_CHANGE,
    ACTION_DELETE,
    ACTION_PROVISION,
    ACTION_RENAME,
    DeviceService,
    build_qr_payload,
    device_display_name,
    render_qr_png,
)
from app.services.node_assignment import NoCapacityError

# Tables needed for these tests. The full metadata pulls in Postgres-only DDL.
_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    MqttNode.__table__,
    DeviceGroup.__table__,
    Device.__table__,
    MqttCredential.__table__,
    DeviceUserAssignment.__table__,
    ActivityLog.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Adapt Postgres-only DDL so the tables compile on the SQLite test engine.

    - swap ``gen_random_uuid()`` PK defaults for a Python ``uuid4`` default
    - render the ``activity_logs.detail`` JSONB column as the generic JSON type
      (SQLite has no JSONB compiler)
    """
    from sqlalchemy import JSON

    for table in _TEST_TABLES:
        if "id" in table.c:
            id_col = table.c.id
            id_col.server_default = None
            id_col.default = ColumnDefault(lambda: uuid.uuid4())
    # Activity log ``detail`` is JSONB on Postgres; use generic JSON for SQLite.
    ActivityLog.__table__.c.detail.type = JSON()


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


async def _seed_org_with_node(
    session: AsyncSession, *, capacity: int = 10, active: int = 0
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create an org, a user (the actor), and an active MQTT node."""
    org = Organization(name="Org A", type="project_center", plan="free")
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email="pc@example.com", role=ROLE_PROJECT_CENTER)
    session.add(user)
    node = MqttNode(
        ip="127.0.0.1", port=1883, capacity=capacity,
        active_connections=active, status="active",
    )
    session.add(node)
    await session.flush()
    return org.id, user.id, node.id


def _scope(session: AsyncSession, org_id, user_id, role=ROLE_PROJECT_CENTER) -> TenantScope:
    principal = Principal(user_id=str(user_id), org_id=str(org_id), role=role)
    return TenantScope(principal, session)


async def _activity_actions(session: AsyncSession) -> list[str]:
    rows = await session.execute(select(ActivityLog.action))
    return [r[0] for r in rows.all()]


async def _activity_logs(session: AsyncSession) -> list[ActivityLog]:
    rows = await session.execute(select(ActivityLog))
    return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# Provisioning (Req 5.1, 5.2, 5.8, 24.4)
# ---------------------------------------------------------------------------
async def test_provision_creates_device_with_unique_credentials(session):
    org_id, user_id, node_id = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))

    device, credential, secret = await service.provision_device(label="Pump")

    assert device.org_id == org_id
    assert device.label == "Pump"
    assert device.node_id == node_id  # bound to an MQTT node (Req 24.4)
    assert device.device_uid  # hardware/QR identity generated

    # Unique MQTT credential with org-scoped ACL (Req 3.5, 5.1).
    assert credential.device_id == device.id
    assert credential.acl_pattern == f"iotaps/{org_id}/#"
    assert credential.revoked is False
    # Secret is returned once and only its hash is stored.
    assert secret
    assert credential.password_hash != secret
    assert password_service.verify_password(secret, credential.password_hash)

    assert ACTION_PROVISION in await _activity_actions(session)


async def test_provision_activity_log_records_node_and_uid(session):
    org_id, user_id, node_id = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="Pump")

    logs = await _activity_logs(session)
    provision = next(log for log in logs if log.action == ACTION_PROVISION)
    assert provision.org_id == org_id
    assert provision.user_id == user_id
    assert provision.device_id == device.id
    assert provision.detail == {
        "device_uid": device.device_uid,
        "node_id": str(node_id),
    }


def test_activity_log_action_constants_are_distinct():
    # The task requires distinct activity-log entries for provisioning,
    # assignment, rename, command, and config change (Req 5.8).
    actions = {
        ACTION_PROVISION,
        ACTION_ASSIGN,
        ACTION_RENAME,
        ACTION_COMMAND,
        ACTION_CONFIG_CHANGE,
        ACTION_DELETE,
    }
    assert len(actions) == 6


async def test_provision_credentials_are_unique_across_devices(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))

    _, cred_a, secret_a = await service.provision_device(label="A")
    _, cred_b, secret_b = await service.provision_device(label="B")

    assert cred_a.username != cred_b.username
    assert secret_a != secret_b


async def test_provision_raises_when_no_node_capacity(session):
    org_id, user_id, _ = await _seed_org_with_node(session, capacity=1, active=1)
    service = DeviceService(_scope(session, org_id, user_id))

    with pytest.raises(NoCapacityError):
        await service.provision_device(label="NoRoom")


# ---------------------------------------------------------------------------
# QR encoding (Req 5.2)
# ---------------------------------------------------------------------------
async def test_qr_payload_encodes_device_identity(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="Sensor")

    payload = build_qr_payload(device)
    assert str(device.id) in payload
    assert str(org_id) in payload
    assert device.device_uid in payload


async def test_qr_png_is_valid_png(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="Sensor")

    png = await service.generate_qr_png(device.id)
    # PNG magic number.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_qr_png_pure():
    png = render_qr_png("iotaps:device?id=abc")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Rename / label override (Req 5.3, 5.4, 5.8)
# ---------------------------------------------------------------------------
async def test_rename_updates_label_and_logs(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="old")

    updated = await service.update_device(device.id, label="new", label_set=True)
    assert updated.label == "new"
    assert ACTION_RENAME in await _activity_actions(session)


async def test_rename_logs_old_and_new_label(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="old")

    await service.update_device(device.id, label="new", label_set=True)

    logs = await _activity_logs(session)
    rename = next(log for log in logs if log.action == ACTION_RENAME)
    assert rename.device_id == device.id
    assert rename.detail == {"old_label": "old", "new_label": "new"}


async def test_rename_to_same_label_does_not_log(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="same")

    await service.update_device(device.id, label="same", label_set=True)

    assert ACTION_RENAME not in await _activity_actions(session)


# ---------------------------------------------------------------------------
# Label override displayed in place of the default identifier (Req 5.4)
# ---------------------------------------------------------------------------
async def test_custom_label_displayed_in_place_of_identifier(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(
        label="Front Gate", device_uid="esp32-abc123"
    )

    # With a label set, the label is shown instead of the hardware uid.
    assert device_display_name(device) == "Front Gate"


def test_display_name_falls_back_to_device_uid_when_no_label():
    device = Device(
        org_id=uuid.uuid4(),
        device_uid="esp32-xyz789",
        label=None,
        status="offline",
    )
    assert device_display_name(device) == "esp32-xyz789"


def test_display_name_ignores_blank_label():
    device = Device(
        org_id=uuid.uuid4(),
        device_uid="esp32-blank",
        label="   ",
        status="offline",
    )
    # A whitespace-only label is not a meaningful override; fall back to uid.
    assert device_display_name(device) == "esp32-blank"


# ---------------------------------------------------------------------------
# Group association (Req 5.5)
# ---------------------------------------------------------------------------
async def test_create_group_and_associate_device(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    group = await service.create_group("Tanks")
    assert group.org_id == org_id

    device, _, _ = await service.provision_device(label="d")
    updated = await service.update_device(
        device.id, group_id=group.id, group_set=True
    )
    assert updated.group_id == group.id
    assert ACTION_CONFIG_CHANGE in await _activity_actions(session)

    logs = await _activity_logs(session)
    config = next(log for log in logs if log.action == ACTION_CONFIG_CHANGE)
    assert config.detail == {"group_id": str(group.id)}


# ---------------------------------------------------------------------------
# Maintenance mode (Req 5.7)
# ---------------------------------------------------------------------------
async def test_maintenance_mode_toggle_logs_config_change(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="d")
    # Normalize: SQLite renders the boolean server_default unreliably; the
    # production Postgres default is false. Start from a known false state.
    device.maintenance_mode = False
    await session.commit()

    updated = await service.update_device(device.id, maintenance_mode=True)
    assert updated.maintenance_mode is True
    assert ACTION_CONFIG_CHANGE in await _activity_actions(session)


# ---------------------------------------------------------------------------
# Assignment to a Device_User (Req 5.6, 5.8)
# ---------------------------------------------------------------------------
async def test_assign_device_to_user(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="d")

    du = User(org_id=org_id, email="du@example.com", role=ROLE_DEVICE_USER)
    session.add(du)
    await session.flush()

    assignment = await service.assign_device_to_user(device.id, du.id)
    assert assignment.device_id == device.id
    assert assignment.user_id == du.id
    assert ACTION_ASSIGN in await _activity_actions(session)


async def test_assign_is_idempotent(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="d")
    du = User(org_id=org_id, email="du@example.com", role=ROLE_DEVICE_USER)
    session.add(du)
    await session.flush()

    a1 = await service.assign_device_to_user(device.id, du.id)
    a2 = await service.assign_device_to_user(device.id, du.id)
    assert a1.id == a2.id

    rows = await session.execute(
        select(DeviceUserAssignment).where(
            DeviceUserAssignment.device_id == device.id
        )
    )
    assert len(rows.scalars().all()) == 1


# ---------------------------------------------------------------------------
# Deletion + credential revocation (Req 5.9, 5.8)
# ---------------------------------------------------------------------------
async def test_delete_revokes_credentials_and_removes_device(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, credential, _ = await service.provision_device(label="d")
    cred_id = credential.id
    device_id = device.id

    await service.delete_device(device_id)

    # Device row removed.
    assert await session.get(Device, device_id) is None
    # Credential revoked (Req 5.9). Cascade delete may remove the row; if it
    # remains it must be revoked. Either outcome denies the old credential.
    cred = await session.get(MqttCredential, cred_id)
    assert cred is None or cred.revoked is True
    assert ACTION_DELETE in await _activity_actions(session)


# ---------------------------------------------------------------------------
# Tenant isolation (Req 3.3)
# ---------------------------------------------------------------------------
async def test_cross_org_device_access_denied(session):
    org_id, user_id, _ = await _seed_org_with_node(session)
    service = DeviceService(_scope(session, org_id, user_id))
    device, _, _ = await service.provision_device(label="d")

    from app.core.errors import AuthorizationError

    intruder = DeviceService(
        _scope(session, uuid.uuid4(), uuid.uuid4(), role=ROLE_PROJECT_CENTER)
    )
    with pytest.raises(AuthorizationError):
        await intruder.get_device(device.id)


# ---------------------------------------------------------------------------
# Plan device limit (Req 15.1, 15.7)
# ---------------------------------------------------------------------------
async def test_free_plan_limited_to_two_devices(session):
    org_id, user_id, _ = await _seed_org_with_node(session, capacity=100)
    service = DeviceService(_scope(session, org_id, user_id))

    # Free plan allows exactly two devices.
    await service.provision_device(label="d1")
    await service.provision_device(label="d2")

    from app.services.plan_limits import PlanLimitError

    with pytest.raises(PlanLimitError):
        await service.provision_device(label="d3")


async def test_pro_plan_allows_more_than_two_devices(session):
    # Seed a Pro org so the device cap is lifted (Req 15.2).
    org = Organization(name="Pro Org", type="project_center", plan="pro")
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email="pro@example.com", role=ROLE_PROJECT_CENTER)
    session.add(user)
    node = MqttNode(
        ip="127.0.0.1", port=1883, capacity=100,
        active_connections=0, status="active",
    )
    session.add(node)
    await session.flush()

    service = DeviceService(_scope(session, org.id, user.id))
    for i in range(3):
        await service.provision_device(label=f"d{i}")

    # All three were created (cap lifted for Pro).
    assert await service._count_devices() == 3
