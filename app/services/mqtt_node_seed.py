"""Ensure at least one MQTT node exists for device assignment (dev / single-broker)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.infra import MqttNode
from app.services.node_assignment import ACTIVE_STATUS


async def seed_default_mqtt_node(
    session: AsyncSession,
    *,
    host: str,
    port: int,
    capacity: int,
) -> bool:
    """Create a default active node when the registry is empty.

    Returns True if a new row was inserted.
    """
    host = host.strip()
    if not host or capacity <= 0:
        return False

    count = await session.scalar(select(func.count()).select_from(MqttNode))
    if count and count > 0:
        return False

    session.add(
        MqttNode(
            ip=host,
            port=port,
            capacity=capacity,
            active_connections=0,
            status=ACTIVE_STATUS,
        )
    )
    await session.commit()
    return True
