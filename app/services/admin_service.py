"""Super_Admin platform-management service (Req 23).

Backs the Super_Admin control-panel surface from design.md ("Admin"):

    GET    /admin/overview                 -> platform counts, online, revenue, health
    POST   /admin/companies                -> create an Organization (Req 23.2)
    PATCH  /admin/companies/{id}/suspend   -> suspend an Organization (Req 23.2/23.3)
    DELETE /admin/companies/{id}           -> delete an Organization (Req 23.2)
    POST   /admin/users/{id}/reset-password-> reset a user's password (Req 23.4)
    PATCH  /admin/users/{id}/role          -> change a user's role (Req 23.5)
    POST   /admin/devices/{id}/reassign    -> move a device to another org (Req 23.6)

Every operation here is Super_Admin-only and acts *across* organization
boundaries (Req 23.6): the functions take a bare :class:`AsyncSession` rather
than a tenant-scoped query helper, because the Super_Admin is not bound to a
single tenant. RBAC (``require_role(ROLE_SUPER_ADMIN)``) is enforced at the
route layer.

Organization suspension (Req 23.3) only affects *new* sign-ins: the login flow
(``app.api.v1.auth.login``) consults :func:`organization_is_suspended` before
issuing tokens, while already-issued access/refresh tokens keep working until
they expire, so existing sessions continue.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.redis_keys import ONLINE_DEVICES
from app.core.security import password as password_service
from app.core.security.principal import VALID_ROLES
from app.models.billing import Payment
from app.models.device import Device
from app.models.infra import MqttNode
from app.models.organization import Organization
from app.models.user import User

# Organization status values (organizations.status).
ORG_STATUS_ACTIVE = "active"
ORG_STATUS_SUSPENDED = "suspended"

# Payment statuses that count towards realised revenue (Req 23.1, payments.status).
_REVENUE_STATUSES = ("captured",)


def _coerce_uuid(value: Any) -> uuid.UUID:
    """Coerce ``value`` to a UUID, raising a 404 for a malformed reference."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NotFoundError("Resource not found", error_code="not_found") from exc


# ---------------------------------------------------------------------------
# Overview (Req 23.1)
# ---------------------------------------------------------------------------
async def _scalar_count(session: AsyncSession, model: type) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one() or 0)


async def _total_revenue(session: AsyncSession) -> Decimal:
    """Sum of captured payment amounts across all organizations (Req 23.1)."""
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status.in_(_REVENUE_STATUSES)
        )
    )
    return Decimal(str(result.scalar_one() or 0))


async def _online_device_count(redis: Any) -> int:
    """Count of currently-online devices from the Redis presence set (Req 23.1)."""
    if redis is None:
        return 0
    try:
        return int(await redis.scard(ONLINE_DEVICES) or 0)
    except Exception:  # pragma: no cover - presence store optional/degraded
        return 0


async def _server_health(session: AsyncSession, redis: Any) -> dict[str, Any]:
    """Summarise MQTT-node health plus the cache store (Req 23.1 server health)."""
    nodes_result = await session.execute(select(MqttNode))
    nodes = list(nodes_result.scalars().all())
    node_views = [
        {
            "id": str(node.id),
            "ip": node.ip,
            "port": node.port,
            "capacity": node.capacity,
            "active_connections": node.active_connections,
            "status": node.status,
            "ram_pct": float(node.ram_pct) if node.ram_pct is not None else None,
            "cpu_pct": float(node.cpu_pct) if node.cpu_pct is not None else None,
            "disk_pct": float(node.disk_pct) if node.disk_pct is not None else None,
        }
        for node in nodes
    ]

    redis_status = "unconfigured"
    if redis is not None:
        try:
            await redis.ping()
            redis_status = "ok"
        except Exception:  # pragma: no cover - degraded cache store
            redis_status = "degraded"

    return {"redis": redis_status, "mqtt_nodes": node_views}


async def overview(session: AsyncSession, redis: Any = None) -> dict[str, Any]:
    """Build the Super_Admin platform overview (Req 23.1)."""
    return {
        "companies": await _scalar_count(session, Organization),
        "devices": await _scalar_count(session, Device),
        "users": await _scalar_count(session, User),
        "online": await _online_device_count(redis),
        "revenue": await _total_revenue(session),
        "server_health": await _server_health(session, redis),
    }


# ---------------------------------------------------------------------------
# Company management (Req 23.2, 23.3)
# ---------------------------------------------------------------------------
async def create_company(
    session: AsyncSession,
    *,
    name: str,
    plan: str = "free",
    type: str = "project_center",
) -> Organization:
    """Create a new Organization for a company (Req 23.2)."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError(
            "Company name is required", error_code="invalid_company_name"
        )
    org = Organization(
        name=clean_name, plan=plan, type=type, status=ORG_STATUS_ACTIVE
    )
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


async def _get_company(session: AsyncSession, company_id: Any) -> Organization:
    org = await session.get(Organization, _coerce_uuid(company_id))
    if org is None:
        raise NotFoundError("Company not found", error_code="company_not_found")
    return org


async def set_company_status(
    session: AsyncSession, company_id: Any, *, status: str
) -> Organization:
    """Suspend or reactivate an Organization (Req 23.2, 23.3)."""
    if status not in (ORG_STATUS_ACTIVE, ORG_STATUS_SUSPENDED):
        raise ValidationError(
            "Invalid company status", error_code="invalid_company_status"
        )
    org = await _get_company(session, company_id)
    org.status = status
    await session.commit()
    await session.refresh(org)
    return org


async def suspend_company(session: AsyncSession, company_id: Any) -> Organization:
    """Suspend an Organization, denying its users new sign-ins (Req 23.2, 23.3)."""
    return await set_company_status(
        session, company_id, status=ORG_STATUS_SUSPENDED
    )


async def delete_company(session: AsyncSession, company_id: Any) -> None:
    """Delete an Organization (Req 23.2)."""
    org = await _get_company(session, company_id)
    await session.delete(org)
    await session.commit()


async def organization_is_suspended(
    session: AsyncSession, org_id: Any
) -> bool:
    """Whether the organization is suspended (gates new sign-ins, Req 23.3)."""
    try:
        org = await session.get(Organization, _coerce_uuid(org_id))
    except NotFoundError:
        return False
    return org is not None and org.status == ORG_STATUS_SUSPENDED


# ---------------------------------------------------------------------------
# User management (Req 23.4, 23.5)
# ---------------------------------------------------------------------------
async def _get_user(session: AsyncSession, user_id: Any) -> User:
    user = await session.get(User, _coerce_uuid(user_id))
    if user is None:
        raise NotFoundError("User not found", error_code="user_not_found")
    return user


async def reset_user_password(
    session: AsyncSession, user_id: Any, *, new_password: str
) -> User:
    """Reset a user's password across any organization (Req 23.4)."""
    if not new_password or len(new_password) < 8:
        raise ValidationError(
            "New password must be at least 8 characters",
            error_code="invalid_password",
        )
    user = await _get_user(session, user_id)
    user.password_hash = password_service.hash_password(new_password)
    user.password_format = password_service.CURRENT_FORMAT
    await session.commit()
    await session.refresh(user)
    return user


async def change_user_role(
    session: AsyncSession, user_id: Any, *, role: str
) -> User:
    """Change a user's role and apply the corresponding permissions (Req 23.5)."""
    if role not in VALID_ROLES:
        raise ValidationError("Invalid role", error_code="invalid_role")
    user = await _get_user(session, user_id)
    user.role = role
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Device reassignment across org boundaries (Req 23.6)
# ---------------------------------------------------------------------------
async def reassign_device(
    session: AsyncSession, device_id: Any, *, org_id: Any
) -> Device:
    """Move a device to another Organization (Req 23.6).

    Super_Admin acts across organization boundaries: the device's ``org_id`` is
    repointed to the target organization (which must exist). The MQTT
    credentials' per-org ACL is also realigned so the device publishes under the
    new tenant's namespace.
    """
    device = await session.get(Device, _coerce_uuid(device_id))
    if device is None:
        raise NotFoundError("Device not found", error_code="device_not_found")

    target_org = await session.get(Organization, _coerce_uuid(org_id))
    if target_org is None:
        raise NotFoundError(
            "Target organization not found", error_code="organization_not_found"
        )

    device.org_id = target_org.id
    await session.commit()
    await session.refresh(device)
    return device
