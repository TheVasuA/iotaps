"""Dashboard and widget management service (Task 8.1, Req 7).

Encapsulates the business logic behind the Dashboards & Widgets API
(design.md "Dashboards & Widgets"):

    - create / list / get / update (name, layout) dashboards
    - add widgets to a dashboard
    - update a widget's config, layout, pinned state, and chart annotations

The service is transport-agnostic: it takes a :class:`TenantScope` (which
carries the request principal + DB session and enforces tenant isolation) and
raw values, and returns ORM objects. The HTTP router
(``app.api.v1.dashboards``) maps these to request/response schemas.

Key invariants:
  - Every dashboard and widget is created under the caller's ``org_id`` and all
    reads go through :class:`TenantScope`, so they are auto-filtered to the
    caller's organization (Req 3.2, 3.3).
  - A dashboard's grid layout (React Grid Layout) is persisted on update so a
    user's arrangement survives reloads (Req 7.1, 7.2).
  - A widget's pinned/favorite state (Req 7.5) and chart annotations (Req 7.6)
    are persisted alongside its config and per-widget layout.
  - A widget always belongs to a dashboard the caller owns; widget operations
    first resolve the parent dashboard through the tenant scope so a widget in
    another org cannot be reached even by id (Req 3.3).
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.security.tenant import TenantScope
from app.models.dashboard import Dashboard, Widget

# Number of random bytes behind a Public_Dashboard_Link token (Req 8.1). 32
# bytes (~43 url-safe chars) makes the token unguessable.
_PUBLIC_TOKEN_BYTES = 32

# Widget types supported by the platform (design.md widgets.type, Req 7.3).
WIDGET_TYPES = frozenset(
    {
        "line",
        "gauge",
        "bar",
        "value",
        "map",
        "toggle",
        "slider",
        "alert_badge",
    }
)


class DashboardService:
    """Tenant-scoped operations over dashboards and their widgets."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session

    @property
    def _org_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.org_id))

    def _owner_user_uuid(self) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(self._scope.principal.user_id))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Dashboards (Req 7.1, 7.2)
    # ------------------------------------------------------------------
    async def create_dashboard(
        self, *, name: str, layout: dict | None = None
    ) -> Dashboard:
        """Create a dashboard in the caller's org owned by the caller."""
        if not name or not name.strip():
            raise ValidationError(
                "Dashboard name is required", error_code="invalid_dashboard_name"
            )
        dashboard = Dashboard(
            org_id=self._org_uuid,
            owner_user_id=self._owner_user_uuid(),
            name=name.strip(),
            layout=layout,
        )
        self._session.add(dashboard)
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def list_dashboards(self) -> list[Dashboard]:
        """List dashboards in the caller's org (Req 3.2)."""
        stmt = self._scope.select(Dashboard).order_by(Dashboard.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_dashboard(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Fetch a dashboard by id, enforcing tenant ownership (Req 3.3)."""
        return await self._scope.get(Dashboard, dashboard_id)

    async def update_dashboard(
        self,
        dashboard_id: uuid.UUID,
        *,
        name: str | None = None,
        layout: dict | None = None,
        name_set: bool = False,
        layout_set: bool = False,
    ) -> Dashboard:
        """Update a dashboard's name and/or persisted grid layout (Req 7.1, 7.2).

        ``name_set`` / ``layout_set`` distinguish "field omitted" from
        "explicitly provided" so a PATCH that only updates the layout does not
        clobber the name and vice versa.
        """
        dashboard = await self._scope.get(Dashboard, dashboard_id)

        if name_set:
            if name is None or not name.strip():
                raise ValidationError(
                    "Dashboard name is required",
                    error_code="invalid_dashboard_name",
                )
            dashboard.name = name.strip()

        if layout_set:
            dashboard.layout = layout  # persist React Grid Layout (Req 7.1, 7.2)

        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    # ------------------------------------------------------------------
    # Widgets (Req 7.1, 7.2, 7.5, 7.6)
    # ------------------------------------------------------------------
    async def add_widget(
        self,
        dashboard_id: uuid.UUID,
        *,
        type: str,
        config: dict | None = None,
        layout: dict | None = None,
    ) -> Widget:
        """Add a widget to a dashboard the caller owns (Req 7.1, 7.3).

        Resolving the parent dashboard through the tenant scope first guarantees
        widgets are only ever added to dashboards in the caller's org (Req 3.3).
        """
        # Enforce tenant ownership of the parent dashboard before mutating.
        await self._scope.get(Dashboard, dashboard_id)

        if type not in WIDGET_TYPES:
            raise ValidationError(
                f"Unsupported widget type: {type!r}",
                error_code="invalid_widget_type",
            )

        widget = Widget(
            org_id=self._org_uuid,
            dashboard_id=dashboard_id,
            type=type,
            config=config,
            layout=layout,
        )
        self._session.add(widget)
        await self._session.commit()
        await self._session.refresh(widget)
        return widget

    async def _get_widget(
        self, dashboard_id: uuid.UUID, widget_id: uuid.UUID
    ) -> Widget:
        """Fetch a widget, enforcing it belongs to the caller's dashboard.

        The parent dashboard is resolved through the tenant scope (Req 3.3) and
        the widget must reference that exact dashboard, so a widget id from
        another dashboard/org cannot be reached.
        """
        await self._scope.get(Dashboard, dashboard_id)
        widget = await self._session.get(Widget, widget_id)
        if (
            widget is None
            or widget.dashboard_id != dashboard_id
            or not self._scope.owns(widget)
        ):
            raise NotFoundError("Widget not found in this dashboard")
        return widget

    async def update_widget(
        self,
        dashboard_id: uuid.UUID,
        widget_id: uuid.UUID,
        *,
        config: dict | None = None,
        layout: dict | None = None,
        pinned: bool | None = None,
        annotations: list | None = None,
        config_set: bool = False,
        layout_set: bool = False,
        pinned_set: bool = False,
        annotations_set: bool = False,
    ) -> Widget:
        """Update a widget's config, layout, pinned state, and annotations.

        Persists the per-widget grid layout (Req 7.2), the pinned/favorite state
        (Req 7.5), and chart annotations (Req 7.6). The ``*_set`` flags
        distinguish "field omitted" from "explicitly provided" so a partial
        PATCH only touches the fields the caller sent.
        """
        widget = await self._get_widget(dashboard_id, widget_id)

        if config_set:
            widget.config = config
        if layout_set:
            widget.layout = layout  # React Grid Layout position/size (Req 7.2)
        if pinned_set and pinned is not None:
            widget.pinned = pinned  # pin/favorite (Req 7.5)
        if annotations_set:
            # Chart annotations default to an empty list, never null (Req 7.6).
            widget.annotations = annotations if annotations is not None else []

        await self._session.commit()
        await self._session.refresh(widget)
        return widget

    async def list_widgets(self, dashboard_id: uuid.UUID) -> list[Widget]:
        """List widgets for a dashboard the caller owns (Req 3.2, 3.3)."""
        await self._scope.get(Dashboard, dashboard_id)
        stmt = self._scope.select(Widget).where(Widget.dashboard_id == dashboard_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_widget(
        self, dashboard_id: uuid.UUID, widget_id: uuid.UUID
    ) -> None:
        """Delete a single widget from a dashboard (tenant-scoped)."""
        widget = await self._get_widget(dashboard_id, widget_id)
        await self._session.delete(widget)
        await self._session.commit()

    # ------------------------------------------------------------------
    # Public sharing (Req 8.1, 8.3)
    # ------------------------------------------------------------------
    async def enable_sharing(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Enable a read-only public link for a dashboard (Req 8.1).

        Generates an unguessable ``public_token`` (Public_Dashboard_Link) and
        flags the dashboard public. Re-enabling an already-shared dashboard is
        idempotent: the existing token is preserved so live links keep working.
        The parent dashboard is resolved through the tenant scope, so a caller
        can only share a dashboard in their own organization (Req 3.3).
        """
        dashboard = await self._scope.get(Dashboard, dashboard_id)
        if not dashboard.public_token:
            dashboard.public_token = secrets.token_urlsafe(_PUBLIC_TOKEN_BYTES)
        dashboard.is_public = True
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def disable_sharing(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Revoke a dashboard's public link (Req 8.3).

        Clears ``is_public`` and the ``public_token`` so the previously issued
        Public_Dashboard_Link can no longer resolve to any dashboard - the
        platform must deny access once sharing is disabled (Req 8.3).
        """
        dashboard = await self._scope.get(Dashboard, dashboard_id)
        dashboard.is_public = False
        dashboard.public_token = None
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def delete_dashboard(self, dashboard_id: uuid.UUID) -> None:
        """Delete a dashboard and its widgets (tenant-scoped)."""
        dashboard = await self._scope.get(Dashboard, dashboard_id)
        # Delete all widgets belonging to this dashboard
        stmt = self._scope.select(Widget).where(Widget.dashboard_id == dashboard_id)
        result = await self._session.execute(stmt)
        for widget in result.scalars().all():
            await self._session.delete(widget)
        await self._session.delete(dashboard)
        await self._session.commit()


async def get_public_dashboard(
    session: AsyncSession, public_token: str
) -> tuple[Dashboard, list[Widget]]:
    """Resolve a Public_Dashboard_Link to its dashboard and widgets (Req 8.2).

    This is intentionally *not* tenant-scoped: a Public_Dashboard_Link is served
    without authentication and therefore without a principal/``org_id``. Access
    is gated solely on a matching token whose dashboard is still shared - a
    dashboard whose sharing has been disabled (``is_public = False``, token
    cleared) cannot be resolved, so the route denies access (Req 8.3).

    Raises :class:`NotFoundError` when no shared dashboard matches the token.
    """
    if not public_token:
        raise NotFoundError("Dashboard is not available")
    stmt = select(Dashboard).where(
        Dashboard.public_token == public_token,
        Dashboard.is_public.is_(True),
    )
    result = await session.execute(stmt)
    dashboard = result.scalar_one_or_none()
    if dashboard is None:
        raise NotFoundError("Dashboard is not available")

    widgets_result = await session.execute(
        select(Widget).where(Widget.dashboard_id == dashboard.id)
    )
    return dashboard, list(widgets_result.scalars().all())
