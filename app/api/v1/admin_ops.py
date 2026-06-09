"""Admin operations API: health, errors, security, settings (Task 20.5).

Super_Admin-only operational surface from design.md ("Admin", Req 28-29):

    GET   /admin/health      -> [service statuses]                  (Req 28.1)
    GET   /admin/errors      -> {recent, trends}                    (Req 28.3)
    GET   /admin/security    -> {login_attempts, blocked_ips, audit_log}  (Req 29.2)
    PATCH /admin/settings    {pricing?, jwt_expiry?, ...} -> {settings}    (Req 29.4)
    GET   /admin/settings    -> {settings}                          (Req 29.4)
    GET   /admin/resources   -> {storage, ram, cdn}                 (Req 29.1)
    GET   /admin/backups     -> {snapshot controls}                 (Req 29.6)
    GET   /admin/marketing   -> {lead_pipeline, marketing_tools}    (Req 29.5)

Error recording (Req 28.2, 28.4) and IP blocking on repeated failed logins
(Req 29.3) are implemented in :mod:`app.services.admin_ops_service` and consumed
by the platform's error handlers / auth flow respectively; this router exposes
the read/admin surface over that data.

Every route requires the Super_Admin role (Req 2.5).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.services import admin_ops_service

router = APIRouter(prefix="/admin", tags=["admin", "ops"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ServiceStatus(BaseModel):
    name: str
    status: str  # ok | degraded | unconfigured


class HealthResponse(BaseModel):
    services: list[ServiceStatus]


class ErrorEntry(BaseModel):
    id: str
    error_code: str | None = None
    message: str
    user_id: str | None = None
    org_id: str | None = None
    device_id: str | None = None
    detail: dict | None = None
    created_at: str | None = None


class ErrorTrendPoint(BaseModel):
    date: str
    count: int


class ErrorsResponse(BaseModel):
    recent: list[ErrorEntry]
    trends: list[ErrorTrendPoint]


class LoginAttemptEntry(BaseModel):
    id: str
    ip: str | None = None
    email: str | None = None
    success: bool
    created_at: str | None = None


class BlockedIpEntry(BaseModel):
    id: str
    ip: str
    reason: str | None = None
    blocked_until: str | None = None
    created_at: str | None = None


class AuditLogEntry(BaseModel):
    id: str
    actor_user_id: str | None = None
    action: str
    detail: dict | None = None
    created_at: str | None = None


class SecurityResponse(BaseModel):
    login_attempts: list[LoginAttemptEntry]
    blocked_ips: list[BlockedIpEntry]
    audit_log: list[AuditLogEntry]


class SettingsUpdateRequest(BaseModel):
    """Platform settings to apply platform-wide immediately (Req 29.4).

    Free-form key/value updates - pricing, plan limits, JWT expiry, rate limits,
    2FA policy, themes, etc. At least one key is required.
    """

    updates: dict[str, Any] = Field(
        ..., description="Setting key -> value pairs to apply", min_length=1
    )

    model_config = {"extra": "forbid"}


class SettingsResponse(BaseModel):
    settings: dict[str, Any]


# ---------------------------------------------------------------------------
# Health (Req 28.1)
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse)
async def admin_health(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    """Return the status of each platform service (Req 28.1)."""
    statuses = await admin_ops_service.service_statuses(session)
    return HealthResponse(services=[ServiceStatus(**s) for s in statuses])


# ---------------------------------------------------------------------------
# Errors (Req 28.3)
# ---------------------------------------------------------------------------
@router.get("/errors", response_model=ErrorsResponse)
async def admin_errors(
    limit: int = Query(default=50, ge=1, le=500),
    days: int = Query(default=7, ge=1, le=90),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ErrorsResponse:
    """Return recent errors and error trends over time (Req 28.3)."""
    recent = await admin_ops_service.recent_errors(session, limit=limit)
    trends = await admin_ops_service.error_trends(session, days=days)
    return ErrorsResponse(
        recent=[ErrorEntry(**e) for e in recent],
        trends=[ErrorTrendPoint(**t) for t in trends],
    )


# ---------------------------------------------------------------------------
# Security (Req 29.2)
# ---------------------------------------------------------------------------
@router.get("/security", response_model=SecurityResponse)
async def admin_security(
    limit: int = Query(default=50, ge=1, le=500),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> SecurityResponse:
    """Return login attempts, blocked IPs, and the audit log (Req 29.2)."""
    data = await admin_ops_service.security_overview(session, limit=limit)
    return SecurityResponse(
        login_attempts=[LoginAttemptEntry(**a) for a in data["login_attempts"]],
        blocked_ips=[BlockedIpEntry(**b) for b in data["blocked_ips"]],
        audit_log=[AuditLogEntry(**a) for a in data["audit_log"]],
    )


# ---------------------------------------------------------------------------
# Settings (Req 29.4)
# ---------------------------------------------------------------------------
@router.get("/settings", response_model=SettingsResponse)
async def get_admin_settings(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> SettingsResponse:
    """Return all current platform settings (Req 29.4)."""
    return SettingsResponse(settings=await admin_ops_service.all_settings())


@router.patch("/settings", response_model=SettingsResponse)
async def patch_admin_settings(
    payload: SettingsUpdateRequest,
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> SettingsResponse:
    """Apply platform settings platform-wide immediately (Req 29.4).

    Each provided setting is written through the settings loader, whose
    read-through Redis cache makes the change effective across every stateless
    app server at once. Returns all settings after applying the updates.
    """
    await admin_ops_service.apply_settings(payload.updates)
    return SettingsResponse(settings=await admin_ops_service.all_settings())


# ---------------------------------------------------------------------------
# Resources / backups / marketing (Req 29.1, 29.5, 29.6)
# ---------------------------------------------------------------------------
@router.get("/resources")
async def admin_resources(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict[str, Any]:
    """Return storage, RAM, and CDN/Cloudflare management controls (Req 29.1)."""
    return await admin_ops_service.resource_controls()


@router.get("/backups")
async def admin_backups(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict[str, Any]:
    """Return Contabo snapshot backup controls (Req 29.6)."""
    return await admin_ops_service.backup_controls()


@router.get("/marketing")
async def admin_marketing(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the enterprise lead pipeline and marketing tools (Req 29.5)."""
    return await admin_ops_service.marketing_overview(session)
