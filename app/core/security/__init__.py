"""Security primitives for the IoTAPS platform.

This package holds cross-cutting security building blocks used by the
Auth_Service and related components:

- ``password`` - one-way salted password hashing/verification with
  ``password_format`` tracking and the force-reset rule for legacy or
  invalid formats (Req 1.7, 1.9).
- ``jwt`` - access-token issuance/verification and refresh-token lifecycle
  (Req 1.1-1.6).
- The middleware stack (Req 2, 3): ``rate_limit_middleware`` (stage 1) plus the
  ``deps`` dependencies for JWT verification, RBAC (``require_role``), tenant
  scoping (``tenant_scope`` / :class:`tenant.TenantScope`), and Device_User
  device-access restriction.
"""

from app.core.security.deps import (
    get_principal,
    require_device_access,
    require_role,
    tenant_scope,
    user_has_device_access,
)
from app.core.security.password import (
    CURRENT_FORMAT,
    SUPPORTED_FORMATS,
    hash_password,
    needs_rehash,
    needs_reset,
    verify_password,
)
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    VALID_ROLES,
    Principal,
)
from app.core.security.tenant import TenantScope

__all__ = [
    # password
    "CURRENT_FORMAT",
    "SUPPORTED_FORMATS",
    "hash_password",
    "needs_rehash",
    "needs_reset",
    "verify_password",
    # principal / roles
    "Principal",
    "ROLE_SUPER_ADMIN",
    "ROLE_PROJECT_CENTER",
    "ROLE_DEVICE_USER",
    "VALID_ROLES",
    # middleware-stack dependencies
    "get_principal",
    "require_role",
    "tenant_scope",
    "require_device_access",
    "user_has_device_access",
    "TenantScope",
]
