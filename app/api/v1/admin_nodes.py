"""Admin MQTT node management & monitoring API (Task 20.2, Req 24.1-24.3).

Implements the Super_Admin-only MQTT node registry surface from design.md
("Admin"):

    POST   /admin/mqtt-nodes   {ip, port, capacity} -> register a node   (Req 24.1)
    DELETE /admin/mqtt-nodes/{id}                    -> deregister a node (Req 24.2)
    GET    /admin/mqtt-nodes   -> [{ram, cpu, disk, connections, ...}]    (Req 24.3)

A registered node is created with ``status='active'`` so the capacity-based
device assignment algorithm (:mod:`app.services.node_assignment`) immediately
considers it eligible (Req 24.1, 24.4). Deregistering removes the node from the
registry so it is no longer assigned new devices (Req 24.2). The list endpoint
surfaces each node's per-node RAM/CPU/disk percentages plus its live active
connection count and capacity for overload monitoring (Req 24.3).

All routes are Super_Admin-only (Req 23.6, 26): node management is a
platform-global operation, not tenant-scoped, so it reads/writes the shared
``mqtt_nodes`` registry directly via the request session.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.models.infra import MqttNode
from app.services.node_assignment import ACTIVE_STATUS

router = APIRouter(prefix="/admin", tags=["admin", "mqtt-nodes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MqttNodeCreate(BaseModel):
    """Registration payload for a new MQTT (Mosquitto) node (Req 24.1)."""

    ip: str = Field(min_length=1, description="Node IP address or hostname")
    port: int = Field(gt=0, le=65535, description="MQTT broker port")
    capacity: int = Field(
        gt=0, description="Maximum concurrent device connections for this node"
    )

    model_config = {"extra": "forbid"}


class MqttNodeOut(BaseModel):
    """A node's registry entry plus its per-node resource metrics (Req 24.3)."""

    id: str
    ip: str
    port: int
    capacity: int
    active_connections: int
    status: str | None
    ram_pct: float | None
    cpu_pct: float | None
    disk_pct: float | None


def _node_out(node: MqttNode) -> MqttNodeOut:
    return MqttNodeOut(
        id=str(node.id),
        ip=node.ip,
        port=node.port,
        capacity=node.capacity,
        active_connections=node.active_connections,
        status=node.status,
        ram_pct=float(node.ram_pct) if node.ram_pct is not None else None,
        cpu_pct=float(node.cpu_pct) if node.cpu_pct is not None else None,
        disk_pct=float(node.disk_pct) if node.disk_pct is not None else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/mqtt-nodes", response_model=MqttNodeOut, status_code=201)
async def register_mqtt_node(
    payload: MqttNodeCreate,
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> MqttNodeOut:
    """Register an MQTT node, making it available for device assignment (Req 24.1).

    The node is created ``active`` so capacity-based assignment immediately
    considers it eligible.
    """
    node = MqttNode(
        ip=payload.ip,
        port=payload.port,
        capacity=payload.capacity,
        active_connections=0,
        status=ACTIVE_STATUS,
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return _node_out(node)


@router.delete("/mqtt-nodes/{node_id}", status_code=204, response_class=Response)
async def deregister_mqtt_node(
    node_id: uuid.UUID,
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Deregister an MQTT node from device assignment (Req 24.2).

    Raises 404 when no node with ``node_id`` exists.
    """
    node = await session.get(MqttNode, node_id)
    if node is None:
        raise NotFoundError("MQTT node not found")
    await session.delete(node)
    await session.commit()
    return Response(status_code=204)


@router.get("/mqtt-nodes", response_model=list[MqttNodeOut])
async def list_mqtt_nodes(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[MqttNodeOut]:
    """List nodes with per-node RAM/CPU/disk + active connection metrics (Req 24.3)."""
    result = await session.execute(select(MqttNode).order_by(MqttNode.created_at.asc()))
    return [_node_out(node) for node in result.scalars()]
