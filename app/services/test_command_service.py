"""Unit tests for the command service state machine + handlers (Task 9.1, Req 9.4-9.7).

These exercise the pure transition helpers and the Redis-backed ACK / timeout /
reconnect-flush handlers with ``fakeredis`` (no live broker/Redis), plus the
``CommandService.issue_command`` online/offline branching with an in-memory
``TenantScope`` over SQLite.
"""

from __future__ import annotations

import json
import uuid

import fakeredis.aioredis
import pytest
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

import app.models  # noqa: F401  register models
from app.core import redis_keys as rk
from app.core.errors import ValidationError
from app.core.security.principal import ROLE_PROJECT_CENTER, Principal
from app.core.security.tenant import TenantScope
from app.db.base import Base
from app.models.device import Device
from app.models.ops import ActivityLog
from app.models.organization import Organization
from app.services import command_service as cs
from app.services.command_service import (
    CommandEvent,
    CommandQueueError,
    CommandRecord,
    CommandService,
    CommandStatus,
    confirm_command,
    expire_command,
    flush_queued_commands,
    next_status,
)


# ---------------------------------------------------------------------------
# Pure transition helper (Property 15 building block)
# ---------------------------------------------------------------------------
def test_legal_transitions():
    assert next_status(None, CommandEvent.ISSUE_ONLINE) is CommandStatus.SENT
    assert next_status(None, CommandEvent.ISSUE_OFFLINE) is CommandStatus.QUEUED
    assert next_status(CommandStatus.SENT, CommandEvent.ACK) is CommandStatus.CONFIRMED
    assert (
        next_status(CommandStatus.SENT, CommandEvent.TIMEOUT)
        is CommandStatus.UNACKNOWLEDGED
    )
    assert (
        next_status(CommandStatus.QUEUED, CommandEvent.RECONNECT_FLUSH)
        is CommandStatus.SENT
    )


@pytest.mark.parametrize(
    "status,event",
    [
        (CommandStatus.CONFIRMED, CommandEvent.ACK),
        (CommandStatus.CONFIRMED, CommandEvent.TIMEOUT),
        (CommandStatus.UNACKNOWLEDGED, CommandEvent.ACK),
        (CommandStatus.QUEUED, CommandEvent.ACK),
        (CommandStatus.SENT, CommandEvent.ISSUE_ONLINE),
    ],
)
def test_illegal_transitions_return_none(status, event):
    assert next_status(status, event) is None


# ---------------------------------------------------------------------------
# Redis-backed handlers
# ---------------------------------------------------------------------------
def _redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _record(command_id: str, status: CommandStatus, device_id: str = "dev1") -> CommandRecord:
    return CommandRecord(
        command_id=command_id,
        device_id=device_id,
        org_id="org1",
        type="on",
        value=None,
        status=status,
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_confirm_sent_command_becomes_confirmed():
    redis = _redis()
    cid = "c1"
    await redis.set(rk.command_record_key(cid), json.dumps(_record(cid, CommandStatus.SENT).to_dict()))

    updated = await confirm_command(redis, cid)
    assert updated is not None and updated.status is CommandStatus.CONFIRMED


@pytest.mark.asyncio
async def test_confirm_unknown_command_is_noop():
    redis = _redis()
    assert await confirm_command(redis, "missing") is None


@pytest.mark.asyncio
async def test_timeout_only_affects_sent_commands():
    redis = _redis()
    # Confirmed command must not be downgraded by a late timeout.
    cid = "c2"
    await redis.set(
        rk.command_record_key(cid),
        json.dumps(_record(cid, CommandStatus.CONFIRMED).to_dict()),
    )
    assert await expire_command(redis, cid) is None

    cid2 = "c3"
    await redis.set(
        rk.command_record_key(cid2),
        json.dumps(_record(cid2, CommandStatus.SENT).to_dict()),
    )
    updated = await expire_command(redis, cid2)
    assert updated is not None and updated.status is CommandStatus.UNACKNOWLEDGED


@pytest.mark.asyncio
async def test_late_ack_after_timeout_is_ignored():
    redis = _redis()
    cid = "c4"
    await redis.set(
        rk.command_record_key(cid),
        json.dumps(_record(cid, CommandStatus.UNACKNOWLEDGED).to_dict()),
    )
    assert await confirm_command(redis, cid) is None


@pytest.mark.asyncio
async def test_flush_queued_commands_publishes_and_marks_sent():
    redis = _redis()
    published: list[tuple[str, str]] = []

    async def publisher(topic: str, payload: str) -> None:
        published.append((topic, payload))

    # Two queued commands for the device.
    for cid in ("q1", "q2"):
        await redis.set(
            rk.command_record_key(cid),
            json.dumps(_record(cid, CommandStatus.QUEUED).to_dict()),
        )
        await redis.rpush(
            rk.command_queue_key("dev1"),
            json.dumps({"command_id": cid, "type": "on", "value": None}),
        )

    flushed = await flush_queued_commands(redis, "org1", "dev1", publisher)

    assert [r.command_id for r in flushed] == ["q1", "q2"]  # FIFO order
    assert all(r.status is CommandStatus.SENT for r in flushed)
    assert len(published) == 2
    # Queue drained.
    assert await redis.llen(rk.command_queue_key("dev1")) == 0


# ---------------------------------------------------------------------------
# CommandService.issue_command (online vs offline)
# ---------------------------------------------------------------------------
def _prepare_tables() -> list:
    tables = [Organization.__table__, Device.__table__, ActivityLog.__table__]
    for table in tables:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    ActivityLog.__table__.c.detail.type = JSON()
    return tables


@pytest.fixture()
async def scope_factory():
    tables = _prepare_tables()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_device(factory, status: str = "online"):
    async with factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        s.add(org)
        await s.flush()
        device = Device(org_id=org.id, device_uid="dev-1", status=status)
        s.add(device)
        await s.flush()
        await s.commit()
        return str(org.id), str(device.id)


def _scope(factory_session, org_id: str) -> TenantScope:
    principal = Principal(user_id=str(uuid.uuid4()), org_id=org_id, role=ROLE_PROJECT_CENTER)
    return TenantScope(principal, factory_session)


@pytest.mark.asyncio
async def test_issue_online_publishes_and_marks_sent(scope_factory):
    org_id, device_id = await _seed_device(scope_factory, status="online")
    redis = _redis()
    await redis.sadd(rk.ONLINE_DEVICES, device_id)
    published: list[tuple[str, str]] = []

    async def publisher(topic: str, payload: str) -> None:
        published.append((topic, payload))

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        record = await service.issue_command(uuid.UUID(device_id), type="on")

    assert record.status is CommandStatus.SENT
    assert len(published) == 1
    # Status record persisted in Redis.
    stored = await redis.get(rk.command_record_key(record.command_id))
    assert json.loads(stored)["status"] == "SENT"


@pytest.mark.asyncio
async def test_issue_offline_queues_and_marks_queued(scope_factory):
    org_id, device_id = await _seed_device(scope_factory, status="offline")
    redis = _redis()  # device not in ONLINE_DEVICES
    published: list[tuple[str, str]] = []

    async def publisher(topic: str, payload: str) -> None:
        published.append((topic, payload))

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        record = await service.issue_command(uuid.UUID(device_id), type="off")

    assert record.status is CommandStatus.QUEUED
    assert published == []  # nothing published while offline
    assert await redis.llen(rk.command_queue_key(device_id)) == 1


@pytest.mark.asyncio
async def test_issue_value_command_requires_value(scope_factory):
    org_id, device_id = await _seed_device(scope_factory)
    redis = _redis()

    async def publisher(topic: str, payload: str) -> None:
        pass

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        with pytest.raises(ValidationError):
            await service.issue_command(uuid.UUID(device_id), type="value")


@pytest.mark.asyncio
async def test_issue_unknown_type_rejected(scope_factory):
    org_id, device_id = await _seed_device(scope_factory)
    redis = _redis()

    async def publisher(topic: str, payload: str) -> None:
        pass

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        with pytest.raises(ValidationError):
            await service.issue_command(uuid.UUID(device_id), type="blink")


@pytest.mark.asyncio
async def test_offline_queue_failure_rejects_command(scope_factory):
    org_id, device_id = await _seed_device(scope_factory, status="offline")
    redis = _redis()

    async def publisher(topic: str, payload: str) -> None:
        pass

    async def failing_rpush(*args, **kwargs):
        raise RuntimeError("redis down")

    redis.rpush = failing_rpush  # type: ignore[assignment]

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        with pytest.raises(CommandQueueError):
            await service.issue_command(uuid.UUID(device_id), type="on")


@pytest.mark.asyncio
async def test_get_command_returns_status(scope_factory):
    org_id, device_id = await _seed_device(scope_factory, status="online")
    redis = _redis()
    await redis.sadd(rk.ONLINE_DEVICES, device_id)

    async def publisher(topic: str, payload: str) -> None:
        pass

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        record = await service.issue_command(uuid.UUID(device_id), type="on")
        fetched = await service.get_command(uuid.UUID(device_id), record.command_id)
    assert fetched.command_id == record.command_id
    assert fetched.status is CommandStatus.SENT


@pytest.mark.asyncio
async def test_end_to_end_online_issue_then_ack(scope_factory):
    org_id, device_id = await _seed_device(scope_factory, status="online")
    redis = _redis()
    await redis.sadd(rk.ONLINE_DEVICES, device_id)

    async def publisher(topic: str, payload: str) -> None:
        pass

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        record = await service.issue_command(uuid.UUID(device_id), type="on")

    confirmed = await confirm_command(redis, record.command_id)
    assert confirmed is not None and confirmed.status is CommandStatus.CONFIRMED


@pytest.mark.asyncio
async def test_schedule_create_and_list(scope_factory):
    org_id, device_id = await _seed_device(scope_factory)
    redis = _redis()

    async def publisher(topic: str, payload: str) -> None:
        pass

    async with scope_factory() as session:
        service = CommandService(_scope(session, org_id), redis, publisher)
        schedule = await service.create_schedule(
            uuid.UUID(device_id), cron="0 8 * * *", type="on"
        )
        listed = await service.list_schedules(uuid.UUID(device_id))

    assert schedule["cron"] == "0 8 * * *"
    assert len(listed) == 1
    assert listed[0]["schedule_id"] == schedule["schedule_id"]
