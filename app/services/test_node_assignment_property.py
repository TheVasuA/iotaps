"""Property-based test for device-to-node assignment by capacity (Task 4.4).

# Feature: iotaps-platform, Property 18: Device-to-node assignment never exceeds capacity

Property 18 (design.md "Correctness Properties"):

    For any set of MQTT nodes with configured capacities and for any sequence of
    device assignments, no node's active connection count ever exceeds its
    capacity, and an assignment fails only when every node is at capacity.

Validates: Requirements 24.4, 32.2

Uses an in-memory SQLite async engine (aiosqlite), mirroring
``test_node_assignment.py``: only the ``mqtt_nodes`` table is created, and the
Postgres ``gen_random_uuid()`` PK default is swapped for a Python ``uuid4`` since
SQLite cannot evaluate it in a column DEFAULT. Each Hypothesis example builds a
fresh in-memory DB, seeds the generated nodes, then replays the generated
sequence of assignment attempts.
"""

from __future__ import annotations

import asyncio
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
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


_prepare_tables_for_sqlite()


# ---------------------------------------------------------------------------
# Generators: constrain to the input space intelligently.
# ---------------------------------------------------------------------------
# A node spec: a configured capacity (>=1) and whether it is active. Inactive
# nodes contribute no usable capacity even though capacity > 0.
_node_spec = st.fixed_dictionaries(
    {
        "capacity": st.integers(min_value=1, max_value=8),
        "active": st.booleans(),
    }
)


@st.composite
def _scenario(draw: st.DrawFn) -> dict:
    """A fleet of MQTT nodes plus a number of assignment attempts.

    The attempt count can exceed, equal, or fall short of total available
    capacity so the property exercises both the success and exhaustion paths.
    """
    nodes = draw(st.lists(_node_spec, min_size=0, max_size=5))
    usable = sum(n["capacity"] for n in nodes if n["active"])
    # Allow attempts to run past total usable capacity so NoCapacity fires.
    n_attempts = draw(st.integers(min_value=0, max_value=usable + 3))
    return {"nodes": nodes, "n_attempts": n_attempts}


# ---------------------------------------------------------------------------
# Async harness: build a fresh in-memory DB per example, seed, replay attempts.
# ---------------------------------------------------------------------------
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
            # Seed the generated fleet.
            for i, spec in enumerate(scenario["nodes"]):
                session.add(
                    MqttNode(
                        ip="127.0.0.1",
                        port=1883,
                        capacity=spec["capacity"],
                        active_connections=0,
                        status="active" if spec["active"] else "inactive",
                    )
                )
            await session.flush()

            usable = sum(
                spec["capacity"] for spec in scenario["nodes"] if spec["active"]
            )

            successes = 0
            for _ in range(scenario["n_attempts"]):
                try:
                    node = await assign_node(session)
                except NoCapacityError:
                    # An assignment may fail ONLY when every node is at capacity,
                    # i.e. we have already consumed all usable capacity.
                    assert successes == usable, (
                        f"NoCapacity raised after {successes} successful "
                        f"assignments but usable capacity is {usable}"
                    )
                    break
                else:
                    successes += 1
                    # No single node may ever exceed its configured capacity.
                    assert node.active_connections <= node.capacity
                    # A successful assignment implies capacity was available.
                    assert successes <= usable, (
                        f"assigned {successes} connections but usable "
                        f"capacity is only {usable}"
                    )

            await session.flush()

            # Global invariant: after the whole sequence, no node exceeds its
            # capacity, and total claimed connections never exceed total usable.
            rows = (await session.execute(select(MqttNode))).scalars().all()
            total_active = 0
            for row in rows:
                assert row.active_connections <= row.capacity, (
                    f"node {row.id} has {row.active_connections} connections "
                    f"but capacity is {row.capacity}"
                )
                total_active += row.active_connections
            assert total_active <= usable
            # Inactive nodes never receive any assignment.
            for row in rows:
                if row.status != "active":
                    assert row.active_connections == 0
    finally:
        await engine.dispose()


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenario=_scenario())
def test_assignment_never_exceeds_capacity(scenario: dict) -> None:
    """Property 18: device-to-node assignment never exceeds capacity.

    Validates: Requirements 24.4, 32.2
    """
    asyncio.run(_run(scenario))
