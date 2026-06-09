"""Unit tests for device-to-node assignment by capacity (Req 24.4, 32.2).

Uses an in-memory SQLite async session (no live Postgres). Only the
``mqtt_nodes`` table is created, and its Postgres-specific ``gen_random_uuid()``
PK default is swapped for a Python uuid4 so SQLite can evaluate it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.db.base import Base
from app.models.infra import MqttNode
from app.services.node_assignment import NoCapacityError, assign_node

_TEST_TABLES = [MqttNode.__table__]


def _prepare_tables_for_sqlite() -> None:
    """Swap the Postgres ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


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


async def _add_node(
    session: AsyncSession,
    *,
    capacity: int,
    active: int = 0,
    status: str = "active",
) -> MqttNode:
    node = MqttNode(
        ip="127.0.0.1",
        port=1883,
        capacity=capacity,
        active_connections=active,
        status=status,
    )
    session.add(node)
    await session.flush()
    return node


async def test_assign_increments_active_connections(session):
    node = await _add_node(session, capacity=5, active=0)

    assigned = await assign_node(session)

    assert assigned.id == node.id
    assert assigned.active_connections == 1


async def test_assign_prefers_least_loaded_node(session):
    busy = await _add_node(session, capacity=10, active=8)
    idle = await _add_node(session, capacity=10, active=1)

    assigned = await assign_node(session)

    assert assigned.id == idle.id
    assert assigned.active_connections == 2
    # The busy node is untouched.
    assert busy.active_connections == 8


async def test_assign_skips_full_and_inactive_nodes(session):
    await _add_node(session, capacity=2, active=2)  # full
    await _add_node(session, capacity=5, active=0, status="inactive")  # not active
    has_room = await _add_node(session, capacity=3, active=1)

    assigned = await assign_node(session)

    assert assigned.id == has_room.id
    assert assigned.active_connections == 2


async def test_assign_raises_no_capacity_when_all_full(session):
    await _add_node(session, capacity=1, active=1)
    await _add_node(session, capacity=3, active=3)

    with pytest.raises(NoCapacityError):
        await assign_node(session)


async def test_assign_raises_no_capacity_when_no_nodes(session):
    with pytest.raises(NoCapacityError):
        await assign_node(session)


async def test_repeated_assignment_never_exceeds_capacity(session):
    await _add_node(session, capacity=2, active=0)
    await _add_node(session, capacity=1, active=0)

    # Three total slots across two nodes; the 4th assignment must fail.
    for _ in range(3):
        await assign_node(session)

    with pytest.raises(NoCapacityError):
        await assign_node(session)

    rows = (await session.execute(select(MqttNode))).scalars().all()
    for node in rows:
        assert node.active_connections <= node.capacity
