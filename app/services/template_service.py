"""Templates catalog and application service (Task 11.1, Req 11, 10.5).

Encapsulates the business logic behind the Templates API (design.md
"Rules & Templates"):

    - list the global template catalog, optionally filtered by category
    - fetch a single template (with its Arduino source + wiring diagram)
    - create a Rule pre-populated from a template (Req 10.5, 11)
    - apply a template to a Device, configuring its Dashboard and Rules from the
      template definition (Req 11.4)

Templates are a *global* catalog (no ``org_id``) shared across all
organizations. Applying a template, however, creates tenant-owned resources
(a Dashboard, its Widgets, and Rules) under the caller's organization, so those
operations go through :class:`TenantScope` and reuse
:class:`~app.services.dashboard_service.DashboardService` and
:class:`~app.services.rule_service.RuleService` (which enforces the per-plan
active-rule limit, Req 10.6-10.8).

Template definition shape (stored as JSONB on the ``templates`` row):

``dashboard_def``::

    {
      "name": "Temperature Monitor",
      "layout": {...},                       # optional React Grid Layout
      "widgets": [
        {"type": "gauge", "config": {...}, "layout": {...}},
        ...
      ]
    }

``rules_def``::

    {
      "rules": [
        {"name": "High temperature alert",
         "enabled": true,
         "nodes": [{"id": "n1", "node_type": "trigger", "config": {...}}, ...],
         "edges": [{"from": "n1", "to": "n2"}]},
        ...
      ]
    }

Both are tolerant: ``dashboard_def`` may be omitted (no dashboard created), and
``rules_def`` may be a bare rule object instead of the ``{"rules": [...]}``
wrapper.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.errors import NotFoundError, ValidationError
from app.core.security.tenant import TenantScope
from app.models.device import Device
from app.models.infra import Template
from app.models.rule import Rule
from app.services.dashboard_service import DashboardService
from app.services.rule_service import RuleService

# Recognised template categories (design.md templates.category, Req 11.1, 11.3).
TEMPLATE_CATEGORIES = frozenset({"student", "company"})


def _normalize_rule_defs(rules_def: dict | list | None) -> list[dict]:
    """Coerce a template's ``rules_def`` into a list of rule definitions.

    Accepts the canonical ``{"rules": [...]}`` wrapper, a bare list of rule
    defs, or a single rule def object. Returns ``[]`` when there is nothing to
    create.
    """
    if not rules_def:
        return []
    if isinstance(rules_def, list):
        return [r for r in rules_def if isinstance(r, dict)]
    if isinstance(rules_def, dict):
        rules = rules_def.get("rules")
        if isinstance(rules, list):
            return [r for r in rules if isinstance(r, dict)]
        # Treat the dict itself as a single rule definition.
        if "nodes" in rules_def or "name" in rules_def:
            return [rules_def]
    return []


class TemplateService:
    """Catalog listing plus template-driven device configuration."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session = scope.session

    # ------------------------------------------------------------------
    # Catalog (Req 11.1, 11.2, 11.3)
    # ------------------------------------------------------------------
    async def list_templates(self, *, category: str | None = None) -> list[Template]:
        """List templates in the global catalog, optionally by category.

        The catalog is not tenant-owned, so no ``org_id`` filter applies; any
        authenticated user can browse the available student/company templates.
        """
        stmt = select(Template)
        if category is not None:
            normalized = category.strip().lower()
            if normalized not in TEMPLATE_CATEGORIES:
                raise ValidationError(
                    f"Unknown template category: {category!r}",
                    error_code="invalid_template_category",
                )
            stmt = stmt.where(Template.category == normalized)
        stmt = stmt.order_by(Template.category, Template.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_template(self, template_id: uuid.UUID) -> Template:
        """Fetch a single template by id (Req 11.2)."""
        template = await self._session.get(Template, template_id)
        if template is None:
            raise NotFoundError("Template not found")
        return template

    # ------------------------------------------------------------------
    # Rule from template (Req 10.5, 11)
    # ------------------------------------------------------------------
    async def create_rule_from_template(self, template_id: uuid.UUID) -> Rule:
        """Create a Rule pre-populated from a template (Req 10.5).

        Uses the first rule definition in the template's ``rules_def``. The
        per-plan active-rule limit is enforced by :class:`RuleService`
        (Req 10.6-10.8).
        """
        template = await self.get_template(template_id)
        rule_defs = _normalize_rule_defs(template.rules_def)
        if not rule_defs:
            raise ValidationError(
                "Template has no rule definition to instantiate",
                error_code="template_has_no_rule",
            )
        first = rule_defs[0]
        rule_service = RuleService(self._scope)
        return await rule_service.create_rule(
            name=first.get("name") or template.name,
            nodes=first.get("nodes") or [],
            edges=first.get("edges") or [],
            enabled=bool(first.get("enabled", True)),
            template_id=template.id,
        )

    # ------------------------------------------------------------------
    # Apply template to device (Req 11.4)
    # ------------------------------------------------------------------
    async def apply_template_to_device(
        self, device_id: uuid.UUID, template_id: uuid.UUID
    ) -> Device:
        """Configure a device's Dashboard and Rules from a template (Req 11.4).

        - Records the applied template on the device (``template_id``).
        - Creates a Dashboard (and its widgets) from ``dashboard_def``.
        - Creates Rules from ``rules_def`` (subject to the plan's active-rule
          limit, Req 10.6-10.8).

        The device is resolved through the tenant scope, so a caller can only
        apply a template to a device in their own organization (Req 3.3).
        """
        device = await self._scope.get(Device, device_id)
        template = await self.get_template(template_id)

        # Record the applied template on the device.
        device.template_id = template.id
        await self._session.flush()

        await self._apply_dashboard(template, device)
        await self._apply_rules(template)

        await self._session.commit()
        await self._session.refresh(device)
        return device

    async def _apply_dashboard(self, template: Template, device: Device) -> None:
        """Create a Dashboard + widgets from the template's ``dashboard_def``.

        Each widget's ``config.deviceId`` is set to the target device so the
        scaffolded dashboard binds to live telemetry immediately (template defs
        omit it because they're device-agnostic).
        """
        dashboard_def = template.dashboard_def
        if not isinstance(dashboard_def, dict):
            return
        dashboard_service = DashboardService(self._scope)
        dashboard = await dashboard_service.create_dashboard(
            name=dashboard_def.get("name") or template.name,
            layout=dashboard_def.get("layout"),
        )
        for widget in dashboard_def.get("widgets") or []:
            if not isinstance(widget, dict) or "type" not in widget:
                continue
            config = dict(widget.get("config") or {})
            config.setdefault("deviceId", str(device.id))
            await dashboard_service.add_widget(
                dashboard.id,
                type=widget["type"],
                config=config,
                layout=widget.get("layout"),
            )

    async def _apply_rules(self, template: Template) -> None:
        """Create Rules from the template's ``rules_def``."""
        rule_service = RuleService(self._scope)
        for rule_def in _normalize_rule_defs(template.rules_def):
            await rule_service.create_rule(
                name=rule_def.get("name") or template.name,
                nodes=rule_def.get("nodes") or [],
                edges=rule_def.get("edges") or [],
                enabled=bool(rule_def.get("enabled", True)),
                template_id=template.id,
            )
