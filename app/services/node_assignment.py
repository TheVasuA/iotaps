"""Device-to-node assignment by capacity (Req 24.4, 32.2).

When a device is provisioned it must be bound to an MQTT (Mosquitto) node that
still has spare connection capacity. This module implements the core selection
algorithm from design.md ("Device-to-Node Assignment by Capacity"):

    def assign_node():
        nodes = mqtt_nodes.where(status='active').order_by(active_connections)
        for n in nodes:
            if n.active_connections < n.capacity:
                n.active_connections += 1
                return n
        raise NoCapacity   # admin must add a node

The function is intentionally narrow: device provisioning (task 4.1) calls
``assign_node(session)`` and persists the returned node id on the device row.
It does not own the surrounding transaction commit, leaving that to the caller.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.infra import MqttNode

# The status value a node must carry to be eligible for assignment. Matches the
# design pseudocode (``where(status='active')``).
ACTIVE_STATUS = "active"


class NoCapacityError(AppError):
    """Raised when every active MQTT node is at its connection capacity.

    This is an operational signal (HTTP 503): the platform is healthy but the
    Super_Admin must add a node before more devices can be provisioned
    (Req 24.4, 32.2).
    """

    error_code = "no_mqtt_capacity"
    status_code = 503

    def __init__(
        self, message: str = "No MQTT node has available capacity; add a node."
    ) -> None:
        super().__init__(message)


# Alias matching the design pseudocode's ``raise NoCapacity``.
NoCapacity = NoCapacityError


async def assign_node(session: AsyncSession) -> MqttNode:
    """Select an active MQTT node with spare capacity and claim one connection.

    Picks the eligible node with the fewest active connections (greedy
    load-balancing), atomically increments its ``active_connections`` using a
    guarded ``UPDATE ... WHERE active_connections < capacity`` so two concurrent
    assignments can never push a node past its capacity, and returns the node.

    Args:
        session: The active async DB session. The caller owns the surrounding
            transaction and is responsible for committing.

    Returns:
        The :class:`MqttNode` the device should be assigned to, with its
        in-memory ``active_connections`` reflecting the increment.

    Raises:
        NoCapacityError: when no active node has ``active_connections < capacity``.
    """
    # Candidate nodes: active and not yet full, fewest connections first so we
    # spread load evenly across the fleet.
    candidates = (
        select(MqttNode)
        .where(
            MqttNode.status == ACTIVE_STATUS,
            MqttNode.active_connections < MqttNode.capacity,
        )
        .order_by(MqttNode.active_connections.asc())
    )

    result = await session.execute(candidates)
    for node in result.scalars():
        # Atomic, capacity-guarded increment. If a concurrent assignment claimed
        # the last slot between our SELECT and this UPDATE, rowcount is 0 and we
        # fall through to the next candidate.
        claim = (
            update(MqttNode)
            .where(
                MqttNode.id == node.id,
                MqttNode.active_connections < MqttNode.capacity,
            )
            .values(active_connections=MqttNode.active_connections + 1)
        )
        claimed = await session.execute(claim)
        if claimed.rowcount == 1:
            # Refresh the in-memory object so the caller sees the new count.
            await session.refresh(node)
            return node

    raise NoCapacityError()
