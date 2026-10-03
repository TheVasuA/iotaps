"""Super-admin bootstrap from SUPERADMIN_EMAIL (and optional SUPERADMIN_PASSWORD)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.user import User


def configured_superadmin_email(settings: Settings | None = None) -> str:
    return (settings or get_settings()).superadmin_email.strip().lower()


def is_configured_superadmin_email(email: str, settings: Settings | None = None) -> bool:
    configured = configured_superadmin_email(settings)
    if not configured:
        return False
    return (email or "").strip().lower() == configured


async def find_user_by_superadmin_email(
    session: AsyncSession, settings: Settings | None = None
) -> User | None:
    configured = configured_superadmin_email(settings)
    if not configured:
        return None
    result = await session.execute(
        select(User).where(func.lower(User.email) == configured)
    )
    return result.scalar_one_or_none()


async def ensure_superadmin_role(session: AsyncSession, user: User) -> bool:
    """Promote the configured email to super_admin. Returns True if role changed."""
    if not is_configured_superadmin_email(user.email):
        return False
    if user.role == "super_admin":
        return False
    user.role = "super_admin"
    await session.commit()
    await session.refresh(user)
    return True
