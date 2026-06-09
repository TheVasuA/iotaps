"""Dashboards & Widgets API endpoints (Task 8.1, Req 7).

Implements the dashboard surface from design.md ("Dashboards & Widgets"):

    GET    /dashboards                     -> [dashboard]
    POST   /dashboards                     {name} -> {dashboard}
    GET    /dashboards/{id}                -> {dashboard, widgets}
    PATCH  /dashboards/{id}                {name?, layout?} -> {dashboard}
    POST   /dashboards/{id}/widgets        {type, config?, layout?} -> {widget}
    PATCH  /dashboards/{id}/widgets/{wid}  {config?, layout?, pinned?, annotations?}
                                           -> {widget}

Dashboards belong to the user that builds them. Management is permitted for any
authenticated user (Project_Center and Device_User build their own dashboards;
Super_Admin is always permitted by ``require_role``). All queries go through
``TenantScope`` so they are auto-filtered to the caller's organization
(Req 3.2, 3.3).

The business logic - persisting the React Grid Layout (Req 7.1, 7.2), pinned
state (Req 7.5), and chart annotations (Req 7.6) - lives in
:class:`~app.services.dashboard_service.DashboardService`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.db.session import get_session
from app.models.dashboard import Dashboard, Widget
from app.services.dashboard_service import DashboardService, get_public_dashboard
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/dashboards", tags=["dashboards"])

# Public, unauthenticated read-only dashboard links (Req 8.2). Mounted under
# /public/dashboards/{token}; this router carries NO auth dependency, and it
# exposes only a GET handler so any mutating action returns 405 (Req 8.4).
public_router = APIRouter(prefix="/public/dashboards", tags=["public-dashboards"])

# Any authenticated platform user may build dashboards (Super_Admin is always
# allowed by require_role); listing the roles documents intent.
_MANAGE_ROLES = (ROLE_PROJECT_CENTER, ROLE_DEVICE_USER, ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class DashboardOut(BaseModel):
    id: str
    org_id: str
    owner_user_id: str | None
    name: str
    is_public: bool
    public_token: str | None
    layout: dict | None


class WidgetOut(BaseModel):
    id: str
    org_id: str
    dashboard_id: str
    type: str
    config: dict | None
    layout: dict | None
    pinned: bool
    annotations: list | None


class CreateDashboardRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    layout: dict | None = None


class UpdateDashboardRequest(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    layout: dict | None = None

    model_config = {"extra": "forbid"}


class CreateWidgetRequest(BaseModel):
    type: str = Field(min_length=1)
    config: dict | None = None
    layout: dict | None = None


class UpdateWidgetRequest(BaseModel):
    config: dict | None = None
    layout: dict | None = None
    pinned: bool | None = None
    annotations: list | None = None

    model_config = {"extra": "forbid"}


class DashboardResponse(BaseModel):
    dashboard: DashboardOut


class DashboardDetailResponse(BaseModel):
    dashboard: DashboardOut
    widgets: list[WidgetOut]


class WidgetResponse(BaseModel):
    widget: WidgetOut


class ShareResponse(BaseModel):
    public_token: str
    url: str


class PublicDashboardOut(BaseModel):
    id: str
    name: str
    layout: dict | None


class PublicWidgetOut(BaseModel):
    id: str
    dashboard_id: str
    type: str
    config: dict | None
    layout: dict | None
    pinned: bool
    annotations: list | None


class PublicDashboardResponse(BaseModel):
    dashboard: PublicDashboardOut
    widgets: list[PublicWidgetOut]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _dashboard_out(dashboard: Dashboard) -> DashboardOut:
    return DashboardOut(
        id=str(dashboard.id),
        org_id=str(dashboard.org_id),
        owner_user_id=(
            str(dashboard.owner_user_id) if dashboard.owner_user_id else None
        ),
        name=dashboard.name,
        is_public=bool(dashboard.is_public),
        public_token=dashboard.public_token,
        layout=dashboard.layout,
    )


def _widget_out(widget: Widget) -> WidgetOut:
    return WidgetOut(
        id=str(widget.id),
        org_id=str(widget.org_id),
        dashboard_id=str(widget.dashboard_id),
        type=widget.type,
        config=widget.config,
        layout=widget.layout,
        pinned=bool(widget.pinned),
        annotations=widget.annotations,
    )


def _public_dashboard_out(dashboard: Dashboard) -> PublicDashboardOut:
    """Serialize a dashboard for a public link, omitting tenant identifiers."""
    return PublicDashboardOut(
        id=str(dashboard.id),
        name=dashboard.name,
        layout=dashboard.layout,
    )


def _public_widget_out(widget: Widget) -> PublicWidgetOut:
    return PublicWidgetOut(
        id=str(widget.id),
        dashboard_id=str(widget.dashboard_id),
        type=widget.type,
        config=widget.config,
        layout=widget.layout,
        pinned=bool(widget.pinned),
        annotations=widget.annotations,
    )


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=list[DashboardOut])
async def list_dashboards(
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> list[DashboardOut]:
    """List dashboards in the caller's organization (Req 3.2)."""
    service = DashboardService(scope)
    dashboards = await service.list_dashboards()
    return [_dashboard_out(d) for d in dashboards]


@router.post("", response_model=DashboardResponse, status_code=201)
async def create_dashboard(
    payload: CreateDashboardRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DashboardResponse:
    """Create a dashboard owned by the caller (Req 7.1)."""
    service = DashboardService(scope)
    dashboard = await service.create_dashboard(
        name=payload.name, layout=payload.layout
    )
    return DashboardResponse(dashboard=_dashboard_out(dashboard))


@router.get("/{dashboard_id}", response_model=DashboardDetailResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DashboardDetailResponse:
    """Fetch a dashboard and its widgets (tenant-scoped, Req 3.3)."""
    service = DashboardService(scope)
    dashboard = await service.get_dashboard(dashboard_id)
    widgets = await service.list_widgets(dashboard_id)
    return DashboardDetailResponse(
        dashboard=_dashboard_out(dashboard),
        widgets=[_widget_out(w) for w in widgets],
    )


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: UpdateDashboardRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DashboardResponse:
    """Rename and/or persist the grid layout for a dashboard (Req 7.1, 7.2)."""
    fields_set = payload.model_fields_set
    service = DashboardService(scope)
    dashboard = await service.update_dashboard(
        dashboard_id,
        name=payload.name,
        layout=payload.layout,
        name_set="name" in fields_set,
        layout_set="layout" in fields_set,
    )
    return DashboardResponse(dashboard=_dashboard_out(dashboard))


# ---------------------------------------------------------------------------
# Public sharing endpoints (Req 8.1, 8.3)
# ---------------------------------------------------------------------------
@router.post("/{dashboard_id}/share", response_model=ShareResponse)
async def share_dashboard(
    dashboard_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> ShareResponse:
    """Enable a read-only public link for a dashboard (Req 8.1).

    Returns the generated ``public_token`` and the shareable URL. The link is
    served without authentication via ``GET /public/dashboards/{token}``.
    """
    service = DashboardService(scope)
    dashboard = await service.enable_sharing(dashboard_id)
    base_url = get_settings().public_base_url.rstrip("/")
    url = f"{base_url}/public/dashboards/{dashboard.public_token}"
    return ShareResponse(public_token=dashboard.public_token or "", url=url)


@router.delete(
    "/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Delete a dashboard and all its widgets (tenant-scoped)."""
    service = DashboardService(scope)
    await service.delete_dashboard(dashboard_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{dashboard_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def unshare_dashboard(
    dashboard_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Revoke a dashboard's public link (Req 8.3).

    Once disabled, the previously issued Public_Dashboard_Link can no longer
    resolve to any dashboard, so subsequent public requests are denied.
    """
    service = DashboardService(scope)
    await service.disable_sharing(dashboard_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
@router.post(
    "/{dashboard_id}/widgets", response_model=WidgetResponse, status_code=201
)
async def add_widget(
    dashboard_id: uuid.UUID,
    payload: CreateWidgetRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> WidgetResponse:
    """Add a widget to a dashboard, placing it on the canvas (Req 7.1, 7.3)."""
    service = DashboardService(scope)
    widget = await service.add_widget(
        dashboard_id,
        type=payload.type,
        config=payload.config,
        layout=payload.layout,
    )
    return WidgetResponse(widget=_widget_out(widget))


@router.patch(
    "/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse
)
async def update_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    payload: UpdateWidgetRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> WidgetResponse:
    """Update a widget's config, layout, pinned state, or annotations.

    Persists the per-widget grid layout (Req 7.2), the pinned/favorite state
    (Req 7.5), and chart annotations (Req 7.6).
    """
    fields_set = payload.model_fields_set
    service = DashboardService(scope)
    widget = await service.update_widget(
        dashboard_id,
        widget_id,
        config=payload.config,
        layout=payload.layout,
        pinned=payload.pinned,
        annotations=payload.annotations,
        config_set="config" in fields_set,
        layout_set="layout" in fields_set,
        pinned_set="pinned" in fields_set,
        annotations_set="annotations" in fields_set,
    )
    return WidgetResponse(widget=_widget_out(widget))


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Delete a single widget from a dashboard."""
    service = DashboardService(scope)
    await service.delete_widget(dashboard_id, widget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public dashboard endpoint (Req 8.2, 8.3, 8.4) - no authentication
# ---------------------------------------------------------------------------
@public_router.get("/{token}", response_model=PublicDashboardResponse)
async def get_public_dashboard_endpoint(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> PublicDashboardResponse:
    """Serve a dashboard read-only via a Public_Dashboard_Link (Req 8.2).

    No authentication is required (Req 8.2). The dashboard is resolved purely by
    its ``public_token`` and only while sharing is enabled; if sharing has been
    disabled the token no longer matches and a not-available (404) response is
    returned (Req 8.3). This router exposes only GET, so any control or
    configuration (mutating) action submitted to the public path returns 405
    Method Not Allowed (Req 8.4).
    """
    dashboard, widgets = await get_public_dashboard(session, token)
    return PublicDashboardResponse(
        dashboard=_public_dashboard_out(dashboard),
        widgets=[_public_widget_out(w) for w in widgets],
    )
