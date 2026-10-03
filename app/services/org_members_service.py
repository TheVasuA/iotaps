"""Org member management (company / multi-user tenants only)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.core.security import password as password_service
from app.core.security.principal import ROLE_DEVICE_USER, ROLE_PROJECT_CENTER
from app.models.organization import Organization
from app.models.user import User
from app.services.account_types import (
    ACCOUNT_COMPANY,
    is_multi_user_org,
    normalize_account_type,
)


async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found", error_code="org_not_found")
    return org


def _assert_can_manage_members(org: Organization, actor: User) -> None:
    if actor.role not in (ROLE_PROJECT_CENTER,):
        raise AuthorizationError(
            "Only organization admins can manage users",
            error_code="org_admin_required",
        )
    if not is_multi_user_org(org.type):
        raise AuthorizationError(
            "User management is available for company organizations only. "
            "Upgrade your account to company to invite team members.",
            error_code="not_company_org",
        )


async def list_org_members(session: AsyncSession, org_id: uuid.UUID) -> list[User]:
    result = await session.execute(
        select(User).where(User.org_id == org_id).order_by(User.created_at.asc())
    )
    return list(result.scalars().all())


async def create_org_member(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: User,
    email: str,
    password: str,
    role: str = ROLE_DEVICE_USER,
) -> User:
    org = await _get_org(session, org_id)
    _assert_can_manage_members(org, actor)

    if role not in (ROLE_DEVICE_USER, ROLE_PROJECT_CENTER):
        raise ValidationError("Invalid member role", error_code="invalid_role")

    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise ValidationError("An account with this email already exists", error_code="email_taken")

    member = User(
        org_id=org_id,
        email=email.strip().lower(),
        gmail_identity=email.strip().lower(),
        password_hash=password_service.hash_password(password),
        password_format=password_service.CURRENT_FORMAT,
        role=role,
        is_org_owner=False,
        twofa_enabled=False,
    )
    session.add(member)
    await session.flush()
    return member


async def upgrade_to_company_org(
    session: AsyncSession,
    *,
    actor: User,
    organization_name: str,
) -> Organization:
    org = await _get_org(session, actor.org_id)
    current = normalize_account_type(org.type)
    if current == ACCOUNT_COMPANY:
        if organization_name.strip():
            org.name = organization_name.strip()
        return org
    if not actor.is_org_owner and actor.role != ROLE_PROJECT_CENTER:
        raise AuthorizationError(
            "Only the workspace owner can upgrade to a company organization",
            error_code="org_owner_required",
        )
    if not organization_name.strip():
        raise ValidationError(
            "Organization name is required",
            error_code="organization_name_required",
        )
    org.type = ACCOUNT_COMPANY
    org.name = organization_name.strip()
    actor.is_org_owner = True
    return org


async def count_org_members(session: AsyncSession, org_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.org_id == org_id)
    )
    return int(result.scalar_one())
