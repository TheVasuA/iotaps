"""Templates API endpoints (Task 11.1, Req 11, 10.5).

Implements the template catalog surface from design.md ("Rules & Templates"):

    GET    /templates                      ?category -> [template]
    GET    /templates/{id}                 -> {template}

The companion mutating endpoints live with their parent resources:

    POST   /rules/from-template            {template_id} -> {rule}   (rules.py)
    POST   /devices/{id}/apply-template    {template_id} -> {device} (devices.py)

The catalog is a *global* (non-tenant) set of student/company project templates,
each carrying Arduino source code and a wiring diagram (Req 11.1-11.3). Any
authenticated user may browse it. The business logic lives in
:class:`~app.services.template_service.TemplateService`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import Principal
from app.core.security.tenant import TenantScope
from app.models.infra import Template
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TemplateOut(BaseModel):
    id: str
    category: str
    name: str
    arduino_code: str | None
    wiring_diagram_url: str | None
    dashboard_def: dict | None
    rules_def: dict | None


def _template_out(template: Template) -> TemplateOut:
    return TemplateOut(
        id=str(template.id),
        category=template.category,
        name=template.name,
        arduino_code=template.arduino_code,
        wiring_diagram_url=template.wiring_diagram_url,
        dashboard_def=template.dashboard_def,
        rules_def=template.rules_def,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=list[TemplateOut])
async def list_templates(
    category: str | None = Query(default=None),
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role()),
) -> list[TemplateOut]:
    """List the template catalog, optionally filtered by category (Req 11.1, 11.3)."""
    service = TemplateService(scope)
    templates = await service.list_templates(category=category)
    return [_template_out(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role()),
) -> TemplateOut:
    """Fetch a single template with its Arduino code + wiring diagram (Req 11.2)."""
    service = TemplateService(scope)
    template = await service.get_template(template_id)
    return _template_out(template)
