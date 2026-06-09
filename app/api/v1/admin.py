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
