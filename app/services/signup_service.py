"""Organization + user creation for self-service signup."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models.organization import Organization
from app.models.user import User
from app.services.account_types import (
    ACCOUNT_COMPANY,
    VALID_ACCOUNT_TYPES,
    default_org_name,
    normalize_account_type,
)
from app.services import referral_service


async def create_signup_organization(
    session: AsyncSession,
    *,
    account_type: str,
    email: str,
    organization_name: str | None = None,
) -> Organization:
    kind = normalize_account_type(account_type)
    if kind not in VALID_ACCOUNT_TYPES:
        raise ValidationError(
            "Invalid account type",
            error_code="invalid_account_type",
        )
    if kind == ACCOUNT_COMPANY and not (organization_name or "").strip():
        raise ValidationError(
            "Organization name is required for company accounts",
            error_code="organization_name_required",
        )

    org = Organization(
        name=default_org_name(kind, email, organization_name),
        type=kind,
        plan="free",
    )
    session.add(org)
    await session.flush()
    return org


async def finalize_new_org(session: AsyncSession, org: Organization, user: User) -> None:
    await referral_service.ensure_referral_code(session, org)
