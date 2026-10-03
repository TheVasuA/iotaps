"""Organization member APIs (company accounts — Blynk-style Users)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import get_principal, require_role, tenant_scope
from app.core.security.principal import ROLE_PROJECT_CENTER, Principal
from app.core.security.tenant import TenantScope
from app.db.session import get_session
from app.models.user import User
from app.services import org_members_service
from app.services.account_types import normalize_account_type

router = APIRouter(prefix="/org", tags=["org"])


class OrgMemberOut(BaseModel):
    id: str
    email: str
    role: str
    is_org_owner: bool
    created_at: datetime | None = None


class CreateOrgMemberRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    role: str = "device_user"


class UpgradeToCompanyRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=120)


def _member_out(user: User) -> OrgMemberOut:
    return OrgMemberOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_org_owner=bool(user.is_org_owner),
        created_at=user.created_at,
    )


@router.get(
    "/members",
    response_model=list[OrgMemberOut],
    dependencies=[Depends(require_role(ROLE_PROJECT_CENTER))],
)
async def list_members(
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[OrgMemberOut]:
    actor = await session.get(User, uuid.UUID(principal.user_id))
    if actor is None:
        return []
    members = await org_members_service.list_org_members(session, actor.org_id)
    return [_member_out(m) for m in members]


@router.post(
    "/members",
    response_model=OrgMemberOut,
    status_code=201,
    dependencies=[Depends(require_role(ROLE_PROJECT_CENTER))],
)
async def create_member(
    payload: CreateOrgMemberRequest,
    scope: TenantScope = Depends(tenant_scope),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> OrgMemberOut:
    actor = await session.get(User, uuid.UUID(principal.user_id))
    member = await org_members_service.create_org_member(
        session,
        org_id=actor.org_id,
        actor=actor,
        email=str(payload.email),
        password=payload.password,
        role=payload.role,
    )
    await session.commit()
    await session.refresh(member)
    return _member_out(member)


@router.post(
    "/upgrade-to-company",
    response_model=OrgMemberOut,
    dependencies=[Depends(require_role(ROLE_PROJECT_CENTER))],
)
async def upgrade_to_company(
    payload: UpgradeToCompanyRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> OrgMemberOut:
    actor = await session.get(User, uuid.UUID(principal.user_id))
    await org_members_service.upgrade_to_company_org(
        session,
        actor=actor,
        organization_name=payload.organization_name,
    )
    await session.commit()
    await session.refresh(actor)
    return _member_out(actor)


class OrgProfileOut(BaseModel):
    account_type: str
    organization_name: str
    can_manage_users: bool
    member_count: int


@router.get("/profile", response_model=OrgProfileOut)
async def org_profile(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> OrgProfileOut:
    from app.models.organization import Organization
    from app.services.account_types import is_multi_user_org

    org = await session.get(Organization, principal.org_id)
    account_type = normalize_account_type(org.type if org else None)
    count = await org_members_service.count_org_members(session, principal.org_id)
    can_manage = (
        principal.role == ROLE_PROJECT_CENTER and is_multi_user_org(account_type)
    )
    return OrgProfileOut(
        account_type=account_type,
        organization_name=org.name if org else "",
        can_manage_users=can_manage,
        member_count=count,
    )
