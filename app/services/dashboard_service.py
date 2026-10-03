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
from app.models.user import User
from app.services.dashboard_settings import normalize_settings

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
        self,
        *,
        name: str,
        layout: dict | None = None,
        settings: dict | None = None,
    ) -> Dashboard:
        """Create a dashboard in the caller's org owned by the caller."""
        if not name or not name.strip():
            raise ValidationError(
                "Dashboard name is required", error_code="invalid_dashboard_name"
            )
        default_settings = {"time_range": "1w", "org_scope": "all", "device_ids": None}
        dashboard = Dashboard(
            org_id=self._org_uuid,
            owner_user_id=self._owner_user_uuid(),
            name=name.strip(),
            layout=layout,
            settings=await normalize_settings(
                self._session,
                self._org_uuid,
                settings,
                default_settings,
            ),
        )
        self._session.add(dashboard)
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    def _user_can_view(self, dashboard: Dashboard, user_id: uuid.UUID) -> bool:
        if dashboard.owner_user_id == user_id:
            return True
        access = (dashboard.settings or {}).get("access") or {}
        uid = str(user_id)
        return uid in (access.get("viewers") or []) or uid in (access.get("editors") or [])

    def _user_can_edit(self, dashboard: Dashboard, user_id: uuid.UUID) -> bool:
        if dashboard.owner_user_id == user_id:
            return True
        access = (dashboard.settings or {}).get("access") or {}
        return str(user_id) in (access.get("editors") or [])

    async def list_dashboards(self) -> list[Dashboard]:
        """List dashboards the caller owns or has been granted access to."""
        from sqlalchemy import select as sa_select

        owner = self._owner_user_uuid()
        if not owner:
            return []
        stmt = sa_select(Dashboard).where(Dashboard.org_id == self._org_uuid).order_by(
            Dashboard.created_at.desc()
        )
        result = await self._session.execute(stmt)
        return [row for row in result.scalars().all() if self._user_can_view(row, owner)]

    async def get_dashboard(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Fetch a dashboard the caller owns or has been granted access to."""
        dashboard = await self._session.get(Dashboard, dashboard_id)
        if dashboard is None or dashboard.org_id != self._org_uuid:
            raise NotFoundError("Dashboard not found")
        owner = self._owner_user_uuid()
        if not owner or not self._user_can_view(dashboard, owner):
            raise NotFoundError("Dashboard not found")
        return dashboard

    async def _require_editor(self, dashboard_id: uuid.UUID) -> Dashboard:
        dashboard = await self.get_dashboard(dashboard_id)
        owner = self._owner_user_uuid()
        if not owner or not self._user_can_edit(dashboard, owner):
            raise NotFoundError("Dashboard not found")
        return dashboard

    async def update_dashboard(
        self,
        dashboard_id: uuid.UUID,
        *,
        name: str | None = None,
        layout: dict | None = None,
        settings: dict | None = None,
        name_set: bool = False,
        layout_set: bool = False,
        settings_set: bool = False,
    ) -> Dashboard:
        """Update a dashboard's name and/or persisted grid layout (Req 7.1, 7.2).

        ``name_set`` / ``layout_set`` distinguish "field omitted" from
        "explicitly provided" so a PATCH that only updates the layout does not
        clobber the name and vice versa.
        """
        dashboard = await self._require_editor(dashboard_id)

        if name_set:
            if name is None or not name.strip():
                raise ValidationError(
                    "Dashboard name is required",
                    error_code="invalid_dashboard_name",
                )
            dashboard.name = name.strip()

        if layout_set:
            dashboard.layout = layout  # persist React Grid Layout (Req 7.1, 7.2)

        if settings_set:
            dashboard.settings = await normalize_settings(
                self._session,
                self._org_uuid,
                settings,
                dashboard.settings,
            )

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
        """Add a widget to a dashboard the caller can edit (Req 7.1, 7.3)."""
        await self._require_editor(dashboard_id)

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
        """Fetch a widget, enforcing it belongs to the caller's dashboard."""
        await self._require_editor(dashboard_id)
        widget = await self._session.get(Widget, widget_id)
        if widget is None or widget.dashboard_id != dashboard_id:
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
        """List widgets for a dashboard the caller owns — per-user isolation."""
        from sqlalchemy import select as sa_select
        # get_dashboard already enforces ownership
        await self.get_dashboard(dashboard_id)
        stmt = sa_select(Widget).where(Widget.dashboard_id == dashboard_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_widget(
        self, dashboard_id: uuid.UUID, widget_id: uuid.UUID
    ) -> None:
        """Delete a single widget from a dashboard (tenant-scoped)."""
        widget = await self._get_widget(dashboard_id, widget_id)
        await self._session.delete(widget)
        await self._session.commit()

    async def get_access(self, dashboard_id: uuid.UUID) -> dict:
        """Org members plus who can view or edit this dashboard. Owner only."""
        dashboard = await self.get_dashboard(dashboard_id)
        owner = self._owner_user_uuid()
        if dashboard.owner_user_id != owner:
            raise NotFoundError("Dashboard not found")
        access = (dashboard.settings or {}).get("access") or {}
        viewers = {str(item) for item in access.get("viewers") or []}
        editors = {str(item) for item in access.get("editors") or []}
        result = await self._session.execute(
            select(User).where(User.org_id == dashboard.org_id).order_by(User.email.asc())
        )
        members = []
        for user in result.scalars().all():
            uid = str(user.id)
            is_owner = user.id == dashboard.owner_user_id
            members.append(
                {
                    "id": uid,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                    "is_owner": is_owner,
                    "can_view": is_owner or uid in viewers or uid in editors,
                    "can_edit": is_owner or uid in editors,
                }
            )
        return {
            "is_public": bool(dashboard.is_public),
            "public_token": dashboard.public_token,
            "members": members,
        }

    async def set_access(
        self,
        dashboard_id: uuid.UUID,
        *,
        viewers: list[str],
        editors: list[str],
    ) -> dict:
        """Replace viewer and editor grants. Owner only. Editors can also view."""
        dashboard = await self.get_dashboard(dashboard_id)
        owner = self._owner_user_uuid()
        if dashboard.owner_user_id != owner:
            raise NotFoundError("Dashboard not found")

        result = await self._session.execute(
            select(User.id).where(User.org_id == dashboard.org_id)
        )
        allowed = {str(row[0]) for row in result.all()}
        owner_id = str(dashboard.owner_user_id) if dashboard.owner_user_id else ""

        def _clean(raw: list[str]) -> list[str]:
            cleaned: list[str] = []
            for item in raw:
                uid = str(item)
                if uid == owner_id:
                    continue
                if uid not in allowed:
                    raise ValidationError(
                        "Access can only be granted to people in this workspace",
                        error_code="invalid_access_user",
                    )
                if uid not in cleaned:
                    cleaned.append(uid)
            return cleaned

        editor_ids = _clean(editors)
        viewer_ids = [uid for uid in _clean(viewers) if uid not in editor_ids]
        settings = dict(dashboard.settings or {})
        settings["access"] = {"viewers": viewer_ids, "editors": editor_ids}
        dashboard.settings = settings
        await self._session.commit()
        await self._session.refresh(dashboard)
        return await self.get_access(dashboard_id)

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
        dashboard = await self._require_editor(dashboard_id)
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
        dashboard = await self._require_editor(dashboard_id)
        dashboard.is_public = False
        dashboard.public_token = None
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def duplicate_dashboard(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Copy a dashboard and its widgets. The copy is private and not a homepage."""
        source = await self._require_editor(dashboard_id)
        widgets = await self.list_widgets(dashboard_id)
        name = await self._unique_copy_name(source.name)
        settings = dict(source.settings or {})
        settings.pop("access", None)
        settings["homepage_users"] = []
        settings["access"] = {"viewers": [], "editors": []}
        copy = Dashboard(
            org_id=self._org_uuid,
            owner_user_id=self._owner_user_uuid(),
            name=name,
            is_public=False,
            layout=dict(source.layout) if isinstance(source.layout, dict) else None,
            settings=settings,
        )
        self._session.add(copy)
        await self._session.flush()
        for widget in widgets:
            self._session.add(
                Widget(
                    org_id=self._org_uuid,
                    dashboard_id=copy.id,
                    type=widget.type,
                    config=dict(widget.config) if isinstance(widget.config, dict) else None,
                    layout=dict(widget.layout) if isinstance(widget.layout, dict) else None,
                    pinned=bool(widget.pinned),
                    annotations=list(widget.annotations or []),
                )
            )
        await self._session.commit()
        await self._session.refresh(copy)
        return copy

    async def _unique_copy_name(self, name: str) -> str:
        from sqlalchemy import select as sa_select

        result = await self._session.execute(
            sa_select(Dashboard.name).where(Dashboard.org_id == self._org_uuid)
        )
        taken = {row[0].lower() for row in result.all() if row[0]}
        base = f"{name} copy"
        candidate = base
        n = 2
        while candidate.lower() in taken:
            candidate = f"{base} {n}"
            n += 1
        return candidate

    async def set_homepage(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Mark this dashboard as the caller's homepage and clear it on the others."""
        dashboard = await self._require_editor(dashboard_id)
        user_id = str(self._owner_user_uuid() or "")
        if not user_id:
            raise NotFoundError("Dashboard not found")
        from sqlalchemy import select as sa_select

        result = await self._session.execute(
            sa_select(Dashboard).where(Dashboard.org_id == self._org_uuid)
        )
        for row in result.scalars().all():
            settings = dict(row.settings or {})
            users = [str(item) for item in settings.get("homepage_users") or [] if item]
            if row.id == dashboard.id:
                if user_id not in users:
                    users.append(user_id)
            elif user_id in users:
                users = [item for item in users if item != user_id]
            else:
                continue
            settings["homepage_users"] = users
            row.settings = settings
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def clear_homepage(self, dashboard_id: uuid.UUID) -> Dashboard:
        """Stop using this dashboard as the caller's homepage."""
        dashboard = await self._require_editor(dashboard_id)
        user_id = str(self._owner_user_uuid() or "")
        if not user_id:
            raise NotFoundError("Dashboard not found")
        settings = dict(dashboard.settings or {})
        settings["homepage_users"] = [
            str(item)
            for item in settings.get("homepage_users") or []
            if item and str(item) != user_id
        ]
        dashboard.settings = settings
        await self._session.commit()
        await self._session.refresh(dashboard)
        return dashboard

    async def delete_dashboard(self, dashboard_id: uuid.UUID) -> None:
        """Delete a dashboard and its widgets (tenant-scoped)."""
        dashboard = await self._require_editor(dashboard_id)
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
