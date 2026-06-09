"""FastAPI security dependencies - middleware stack stages 2-4 (design.md).

Stage 1 (rate limiting) is ASGI middleware (see ``rate_limit_middleware``).
Stages 2-4 are FastAPI dependencies so each route opts into authentication and
declares its role / tenant requirements explicitly:

    2. ``get_principal``      - verify the bearer JWT -> Principal {user_id, org_id, role}
    3. ``require_role(...)``  - RBAC: deny with 403 if the role is not permitted
    4. ``tenant_scope``       - bind org_id to the request-scoped DB session

Additional helper:
    ``require_device_access`` - Device_User may only touch assigned devices
                                (Req 2.4) via ``device_user_assignments``.

Usage in a route::

    @router.get("/devices")
    async def list_devices(
        scope: TenantScope = Depends(tenant_scope),
        _: Principal = Depends(require_role(ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)),
    ):
        rows = await scope.session.execute(scope.select(Device))
        ...
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import jwt as jwt_service
from app.core.security.principal import Principal
from app.core.security.tenant import TenantScope
from app.db.session import get_session
from app.models.device import DeviceUserAssignment


# ---------------------------------------------------------------------------
# Stage 2: JWT verification -> principal (Req 1.3 surface, 2.2)
# ---------------------------------------------------------------------------
def _principal_from_authorization(authorization: str | None) -> Principal:
    """Decode/verify the bearer token and build the request principal."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token", error_code="missing_token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt_service.decode_access_token(token)
    except jwt_service.TokenError as exc:
        raise AuthenticationError(
            "Invalid or expired token", error_code="invalid_token"
        ) from exc
    return Principal.from_claims(claims)


async def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    """FastAPI dependency: the authenticated principal for the request.

    Raises 401 when the bearer token is absent, malformed, expired, or fails
    signature verification.
    """
    return _principal_from_authorization(authorization)


# ---------------------------------------------------------------------------
# Stage 3: RBAC (Req 2.2, 2.3)
# ---------------------------------------------------------------------------
def require_role(*allowed_roles: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Build a dependency that permits only ``allowed_roles`` (deny -> 403).

    Super_Admin is always permitted (Req 2.5: acts across all organizations) in
    addition to any explicitly listed roles. Passing no roles means "any
    authenticated user".
    """
    permitted = frozenset(allowed_roles)

    async def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.is_super_admin:
            return principal
        if permitted and principal.role not in permitted:
            raise AuthorizationError(
                "You do not have permission to perform this action",
                error_code="authorization_error",
            )
        return principal

    return _checker


# ---------------------------------------------------------------------------
# Stage 4: tenant scope (Req 3.2, 3.3, 2.5 bypass)
# ---------------------------------------------------------------------------
async def tenant_scope(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> TenantScope:
    """FastAPI dependency: a tenant-bound query scope for the request.

    Binds the principal's ``org_id`` to the session so ``scope.select(Model)``
    is auto-filtered; Super_Admin bypasses the filter (Req 2.5, 23.6).
    """
    return TenantScope(principal, session)


# ---------------------------------------------------------------------------
# Device_User access restriction (Req 2.4)
# ---------------------------------------------------------------------------
async def user_has_device_access(
    session: AsyncSession, principal: Principal, device_id: str
) -> bool:
    """Whether ``principal`` may access ``device_id``.

    - Super_Admin: yes, across all organizations (Req 2.5).
    - Project_Center: yes for devices in its own organization (tenant filter
      governs which devices that is).
    - Device_User: only devices explicitly assigned via
      ``device_user_assignments`` (Req 2.4).
    """
    if principal.is_super_admin:
        return True

    if not principal.is_device_user:
        # Project_Center: org-level access is enforced by the tenant filter on
        # the device row itself; nothing extra to check here.
        return True

    try:
        device_uuid = uuid.UUID(str(device_id))
        user_uuid = uuid.UUID(str(principal.user_id))
    except (ValueError, TypeError):
        return False

    result = await session.execute(
        select(DeviceUserAssignment.id).where(
            DeviceUserAssignment.device_id == device_uuid,
            DeviceUserAssignment.user_id == user_uuid,
        )
    )
    return result.first() is not None


def require_device_access(
    device_id_param: str = "device_id",
) -> Callable[..., Awaitable[Principal]]:
    """Build a dependency enforcing device access for the path's device id.

    The dependency reads the device id from the matched path parameter named
    ``device_id_param`` (via ``request.path_params``) and raises 403 when a
    Device_User is not assigned to it (Req 2.4). Intended for routes like
    ``/devices/{device_id}/...``.
    """

    async def _checker(
        request: Request,
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
    ) -> Principal:
        device_id = request.path_params.get(device_id_param)
        if device_id is None:
            raise AuthorizationError(
                "Device reference missing", error_code="authorization_error"
            )
        if not await user_has_device_access(session, principal, str(device_id)):
            raise AuthorizationError(
                "You do not have access to this device",
                error_code="authorization_error",
            )
        return principal

    return _checker
