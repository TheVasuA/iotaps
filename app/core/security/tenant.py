"""Tenant-scoped query helper - stage 4 of the middleware stack (design.md).

Multi-tenancy (Req 3) requires that *every* query on behalf of a Project_Center
or Device_User is filtered by the caller's ``org_id`` (Req 3.2), and that a
reference to another org's resource is denied (Req 3.3). Super_Admin bypasses
the filter to act across all organizations (Req 2.5, 23.6).

Rather than relying on callers to remember a ``.where(Model.org_id == ...)``
clause on each query (easy to forget, and a tenant-isolation bug is a security
incident), this module centralises the binding:

- :class:`TenantScope` wraps the request principal and a DB session.
- :meth:`TenantScope.select` returns a SELECT already filtered to the tenant for
  any model that carries ``org_id`` (the :class:`~app.db.base.TenantMixin`).
- :meth:`TenantScope.get` fetches a row by id and enforces it belongs to the
  tenant, raising :class:`AuthorizationError` otherwise (Req 3.3) - note this is
  an *authorization* error regardless of any other reason, per Req 3.3's
  "regardless of any other applicable denial reason".

For a Super_Admin the filter is skipped, so the same call sites work for
cross-org admin operations without special casing.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError
from app.core.security.principal import Principal

T = TypeVar("T")


def _has_org_column(model: type) -> bool:
    return hasattr(model, "org_id")


def _coerce_org_id(org_id: str) -> Any:
    """Coerce the principal's string ``org_id`` to a UUID when possible.

    The JWT carries ``org_id`` as a string, while the DB column is a UUID. The
    UUID type's bind processor expects a ``uuid.UUID``; coercing here keeps the
    comparison correct on both Postgres (asyncpg) and SQLite-backed tests. A
    non-UUID value (defensive) is passed through unchanged.
    """
    try:
        return uuid.UUID(str(org_id))
    except (ValueError, TypeError, AttributeError):
        return org_id


class TenantScope:
    """Binds a request principal's ``org_id`` to a DB session for auto-filtering.

    Constructed once per request (via the ``tenant_scope`` dependency) and
    passed to repository/route code instead of a bare session, so tenant
    filtering is applied consistently and Super_Admin bypass is centralised.
    """

    def __init__(self, principal: Principal, session: AsyncSession) -> None:
        self._principal = principal
        self._session = session

    @property
    def principal(self) -> Principal:
        return self._principal

    @property
    def session(self) -> AsyncSession:
        return self._session

    @property
    def org_id(self) -> str:
        return self._principal.org_id

    @property
    def bypass(self) -> bool:
        """Super_Admin sees all organizations (Req 2.5, 23.6)."""
        return self._principal.is_super_admin

    def select(self, model: type[T]) -> Select:
        """Build a SELECT for ``model`` pre-filtered to the caller's org.

        For a Super_Admin (or a model without ``org_id``) no filter is applied.
        """
        stmt: Select = select(model)
        if self.bypass or not _has_org_column(model):
            return stmt
        return stmt.where(model.org_id == _coerce_org_id(self.org_id))  # type: ignore[attr-defined]

    def owns(self, row: Any) -> bool:
        """Whether ``row`` belongs to the caller's tenant (always True for SA)."""
        if self.bypass or not hasattr(row, "org_id"):
            return True
        return str(row.org_id) == str(self.org_id)

    async def get(self, model: type[T], entity_id: Any) -> T:
        """Fetch ``model`` by primary key, enforcing tenant ownership.

        Raises :class:`AuthorizationError` when the row is missing or belongs to
        another organization (Req 3.3 - denied regardless of any other reason).
        Using a uniform 403 also avoids leaking which ids exist in other orgs.
        """
        row = await self._session.get(model, entity_id)
        if row is None or not self.owns(row):
            raise AuthorizationError(
                "Resource not found in your organization",
                error_code="authorization_error",
            )
        return row
