"""Super_Admin platform control-panel API (Task 20.1, Req 23.1-23.6).

Implements the Super_Admin "Admin" surface from design.md:

    GET    /admin/overview                  -> {companies, devices, users, online,
                                                revenue, server_health}        (Req 23.1)
    POST   /admin/companies                 {name} -> created Organization     (Req 23.2)
    PATCH  /admin/companies/{id}/suspend    -> suspend Organization        (Req 23.2/23.3)
    DELETE /admin/companies/{id}            -> delete Organization             (Req 23.2)
    POST   /admin/users/{id}/reset-password {new_password} -> reset password   (Req 23.4)
    PATCH  /admin/users/{id}/role           {role} -> change role              (Req 23.5)
    POST   /admin/devices/{id}/reassign     {org_id} -> move device cross-org  (Req 23.6)

Every route is gated by ``require_role(ROLE_SUPER_ADMIN)``. The Super_Admin acts
across organization boundaries (Req 23.6), so these routes use a bare DB session
rather than a tenant-scoped query. The actual data operations live in
:mod:`app.services.admin_service`.

Suspending a company (Req 23.3) only blocks *new* sign-ins: the suspension is
checked in the login flow (``app.api.v1.auth.login``); existing sessions keep
working until their tokens expire.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.models.device import Device
from app.models.organization import Organization
from app.models.user import User
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class OverviewResponse(BaseModel):
    companies: int
    devices: int
    users: int
    online: int
    revenue: Decimal
    server_health: dict


class CreateCompanyRequest(BaseModel):
    name: str = Field(min_length=1)
    plan: str = "free"
    type: str = "project_center"

    model_config = {"extra": "forbid"}


class CompanyOut(BaseModel):
    id: str
    name: str
    type: str | None
    plan: str
    status: str


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)

    model_config = {"extra": "forbid"}


class ChangeRoleRequest(BaseModel):
    role: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    org_id: str


class ReassignDeviceRequest(BaseModel):
    org_id: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class DeviceOut(BaseModel):
    id: str
    label: str | None
    org_id: str
    status: str


def _company_out(org: Organization) -> CompanyOut:
    return CompanyOut(
        id=str(org.id),
        name=org.name,
        type=org.type,
        plan=org.plan,
        status=org.status,
    )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.org_id),
    )


def _device_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=str(device.id),
        label=device.label,
        org_id=str(device.org_id),
        status=device.status,
    )


# ---------------------------------------------------------------------------
# Overview (Req 23.1)
# ---------------------------------------------------------------------------
@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> OverviewResponse:
    """Platform-wide counts, online devices, revenue, and server health (Req 23.1)."""
    data = await admin_service.overview(session, get_redis())
    return OverviewResponse(**data)


# ---------------------------------------------------------------------------
# Company management (Req 23.2, 23.3)
# ---------------------------------------------------------------------------
@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(
    payload: CreateCompanyRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> CompanyOut:
    """Create a new company Organization (Req 23.2)."""
    org = await admin_service.create_company(
        session, name=payload.name, plan=payload.plan, type=payload.type
    )
    return _company_out(org)


@router.patch("/companies/{company_id}/suspend", response_model=CompanyOut)
async def suspend_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> CompanyOut:
    """Suspend a company: deny its users new sign-ins (Req 23.2, 23.3)."""
    org = await admin_service.suspend_company(session, company_id)
    return _company_out(org)


@router.delete(
    "/companies/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> Response:
    """Delete a company Organization (Req 23.2)."""
    await admin_service.delete_company(session, company_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# User management (Req 23.4, 23.5)
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/reset-password", response_model=UserOut)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> UserOut:
    """Reset a user's password across any organization (Req 23.4)."""
    user = await admin_service.reset_user_password(
        session, user_id, new_password=payload.new_password
    )
    return _user_out(user)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def change_user_role(
    user_id: uuid.UUID,
    payload: ChangeRoleRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> UserOut:
    """Change a user's role and apply the corresponding permissions (Req 23.5)."""
    user = await admin_service.change_user_role(session, user_id, role=payload.role)
    return _user_out(user)


# ---------------------------------------------------------------------------
# Device reassignment across org boundaries (Req 23.6)
# ---------------------------------------------------------------------------
@router.post("/devices/{device_id}/reassign", response_model=DeviceOut)
async def reassign_device(
    device_id: uuid.UUID,
    payload: ReassignDeviceRequest,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> DeviceOut:
    """Reassign a device to another Organization (Req 23.6)."""
    device = await admin_service.reassign_device(
        session, device_id, org_id=payload.org_id
    )
    return _device_out(device)


# ---------------------------------------------------------------------------
# User listing & management (new)
# ---------------------------------------------------------------------------
class UserDetailOut(BaseModel):
    id: str
    email: str
    role: str
    org_id: str
    created_at: str | None
    device_count: int = 0
    subscription_days_remaining: int | None = None


@router.get("/users", response_model=list[UserDetailOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> list[UserDetailOut]:
    """List all platform users with device counts and subscription status."""
    from sqlalchemy import func, select
    from app.models.billing import Subscription
    from datetime import datetime, timezone

    # Get all users
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())

    output = []
    for user in users:
        # Count devices in user's org
        dev_count_result = await session.execute(
            select(func.count()).select_from(Device).where(Device.org_id == user.org_id)
        )
        device_count = int(dev_count_result.scalar_one() or 0)

        # Check subscription remaining days
        sub_result = await session.execute(
            select(Subscription).where(
                Subscription.org_id == user.org_id,
                Subscription.status == "active",
            ).order_by(Subscription.current_period_end.desc()).limit(1)
        )
        sub = sub_result.scalar_one_or_none()
        days_remaining = None
        if sub and sub.current_period_end:
            delta = sub.current_period_end - datetime.now(timezone.utc)
            days_remaining = max(0, delta.days)

        output.append(UserDetailOut(
            id=str(user.id),
            email=user.email,
            role=user.role,
            org_id=str(user.org_id),
            created_at=str(user.created_at) if hasattr(user, 'created_at') and user.created_at else None,
            device_count=device_count,
            subscription_days_remaining=days_remaining,
        ))
    return output


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> Response:
    """Delete a user and their data."""
    user = await session.get(User, user_id)
    if user is None:
        from app.core.errors import NotFoundError
        raise NotFoundError("User not found")
    await session.delete(user)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Admin Devices Overview (grouped by user)
# ---------------------------------------------------------------------------
class AdminDeviceOut(BaseModel):
    id: str
    label: str | None
    device_uid: str | None
    status: str
    owner_email: str | None
    org_id: str
    subscription_days_remaining: int | None = None
    last_telemetry_at: str | None = None
    node_id: str | None = None
    node_label: str | None = None


@router.get("/devices", response_model=list[AdminDeviceOut])
async def list_all_devices(
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> list[AdminDeviceOut]:
    """List all platform devices with owner, subscription, and MQTT node info."""
    from sqlalchemy import select, func
    from app.models.billing import Subscription
    from app.models.infra import MqttNode
    from datetime import datetime, timezone

    result = await session.execute(
        select(Device, User.email, MqttNode)
        .outerjoin(User, User.org_id == Device.org_id)
        .outerjoin(MqttNode, MqttNode.id == Device.node_id)
        .order_by(Device.created_at.desc())
    )
    rows = result.all()

    output = []
    for device, owner_email, node in rows:
        # Check subscription
        sub_result = await session.execute(
            select(Subscription).where(
                Subscription.org_id == device.org_id,
                Subscription.status == "active",
            ).order_by(Subscription.current_period_end.desc()).limit(1)
        )
        sub = sub_result.scalar_one_or_none()
        days_remaining = None
        if sub and sub.current_period_end:
            delta = sub.current_period_end - datetime.now(timezone.utc)
            days_remaining = max(0, delta.days)

        output.append(AdminDeviceOut(
            id=str(device.id),
            label=device.label,
            device_uid=device.device_uid,
            status=device.status,
            owner_email=owner_email,
            org_id=str(device.org_id),
            subscription_days_remaining=days_remaining,
            node_id=str(node.id) if node is not None else None,
            node_label=f"{node.ip}:{node.port}" if node is not None else None,
        ))
    return output


@router.get("/expiring-subscriptions")
async def expiring_subscriptions(
    days: int = 7,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> list[dict]:
    """List subscriptions expiring within N days."""
    from sqlalchemy import select
    from app.models.billing import Subscription
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) + timedelta(days=days)
    result = await session.execute(
        select(Subscription, User.email).outerjoin(
            User, User.org_id == Subscription.org_id
        ).where(
            Subscription.status == "active",
            Subscription.current_period_end <= cutoff,
            Subscription.current_period_end > datetime.now(timezone.utc),
        ).order_by(Subscription.current_period_end.asc())
    )
    rows = result.all()
    output = []
    for sub, email in rows:
        delta = sub.current_period_end - datetime.now(timezone.utc)
        output.append({
            "subscription_id": str(sub.id),
            "org_id": str(sub.org_id),
            "email": email,
            "plan": sub.plan,
            "days_remaining": max(0, delta.days),
            "expires_at": str(sub.current_period_end),
        })
    return output
