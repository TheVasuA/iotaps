"""Request principal: the authenticated identity attached to a request.

The middleware stack (design.md "Middleware stack") verifies the access JWT and
injects a ``principal {user_id, org_id, role}`` that downstream RBAC checks and
the tenant filter consume. This module defines that principal as a small,
immutable value object derived from :class:`app.core.security.jwt.AccessClaims`.

Keeping it separate from the raw JWT claims lets the rest of the app depend on a
stable, transport-agnostic shape (it does not care that the identity came from a
bearer token) and makes RBAC / tenant-scope logic trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.security.jwt import AccessClaims

# Canonical role names (mirror users.role / JWT ``role`` claim, Req 2.1).
ROLE_SUPER_ADMIN = "super_admin"
ROLE_PROJECT_CENTER = "project_center"
ROLE_DEVICE_USER = "device_user"

VALID_ROLES = frozenset(
    {ROLE_SUPER_ADMIN, ROLE_PROJECT_CENTER, ROLE_DEVICE_USER}
)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller for the current request.

    Attributes:
        user_id: the authenticated user's id (JWT ``sub``).
        org_id: the user's organization/tenant id (JWT ``org_id``).
        role: one of ``super_admin`` / ``project_center`` / ``device_user``.
    """

    user_id: str
    org_id: str
    role: str

    @property
    def is_super_admin(self) -> bool:
        """Super_Admin acts across all organizations (Req 2.5, 23.6)."""
        return self.role == ROLE_SUPER_ADMIN

    @property
    def is_device_user(self) -> bool:
        """Device_User access is restricted to assigned devices (Req 2.4)."""
        return self.role == ROLE_DEVICE_USER

    @classmethod
    def from_claims(cls, claims: AccessClaims) -> "Principal":
        """Build a principal from decoded access-token claims."""
        return cls(user_id=claims.sub, org_id=claims.org_id, role=claims.role)
