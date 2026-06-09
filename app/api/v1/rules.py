"""Rules API endpoints (Task 10.1, Req 10).

Implements the rule surface from design.md ("Rules & Templates"):

    GET    /rules                  -> [rule]
    POST   /rules                  {name, nodes, edges} -> {rule}  (plan limit)
    GET    /rules/{id}             -> {rule, nodes, edges}
    PATCH  /rules/{id}             {name?, enabled?, nodes?, edges?} -> {rule}
    DELETE /rules/{id}             -> 204

Rule management is restricted to Project_Center (and Super_Admin, always
permitted) via ``require_role`` (Req 2.2). All queries go through ``TenantScope``
so they are auto-filtered to the caller's organization (Req 3.2, 3.3).

The per-plan active-rule limit (Free/ambiguous = max 2, Pro = unlimited;
Req 10.6-10.8) is enforced in :class:`~app.services.rule_service.RuleService`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN, Principal
from app.core.security.tenant import TenantScope
from app.models.rule import Rule, RuleEdge, RuleNode
from app.services.rule_service import RuleService
from app.services.template_service import TemplateService

router = APIRouter(prefix="/rules", tags=["rules"])

# Roles permitted to manage rules (Super_Admin is always allowed by require_role).
_MANAGE_ROLES = (ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RuleNodeIn(BaseModel):
    # Client-supplied id used to wire edges within the same request.
    id: str | None = None
    node_type: str = Field(min_length=1)
    config: dict | None = None
    position: dict | None = None


class RuleEdgeIn(BaseModel):
    # References RuleNodeIn.id values in the same payload.
    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class RuleOut(BaseModel):
    id: str
    org_id: str
    name: str
    enabled: bool
    template_id: str | None


class RuleNodeOut(BaseModel):
    id: str
    node_type: str
    config: dict | None
    position: dict | None


class RuleEdgeOut(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str


class CreateRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    enabled: bool = True
    nodes: list[RuleNodeIn] = Field(default_factory=list)
    edges: list[RuleEdgeIn] = Field(default_factory=list)
    template_id: uuid.UUID | None = None


class RuleFromTemplateRequest(BaseModel):
    template_id: uuid.UUID


class UpdateRuleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None
    nodes: list[RuleNodeIn] | None = None
    edges: list[RuleEdgeIn] | None = None

    model_config = {"extra": "forbid"}


class RuleResponse(BaseModel):
    rule: RuleOut


class RuleDetailResponse(BaseModel):
    rule: RuleOut
    nodes: list[RuleNodeOut]
    edges: list[RuleEdgeOut]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _rule_out(rule: Rule) -> RuleOut:
    return RuleOut(
        id=str(rule.id),
        org_id=str(rule.org_id),
        name=rule.name,
        enabled=bool(rule.enabled),
        template_id=str(rule.template_id) if rule.template_id else None,
    )


def _node_out(node: RuleNode) -> RuleNodeOut:
    return RuleNodeOut(
        id=str(node.id),
        node_type=node.node_type,
        config=node.config,
        position=node.position,
    )


def _edge_out(edge: RuleEdge) -> RuleEdgeOut:
    return RuleEdgeOut(
        id=str(edge.id),
        from_node_id=str(edge.from_node_id),
        to_node_id=str(edge.to_node_id),
    )


def _nodes_payload(nodes: list[RuleNodeIn]) -> list[dict]:
    return [
        {
            "id": n.id,
            "node_type": n.node_type,
            "config": n.config,
            "position": n.position,
        }
        for n in nodes
    ]


def _edges_payload(edges: list[RuleEdgeIn]) -> list[dict]:
    return [{"from": e.from_, "to": e.to} for e in edges]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=list[RuleOut])
async def list_rules(
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> list[RuleOut]:
    """List rules in the caller's organization (Req 3.2)."""
    service = RuleService(scope)
    rules = await service.list_rules()
    return [_rule_out(r) for r in rules]


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    payload: CreateRuleRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> RuleResponse:
    """Create a rule from a React Flow graph, enforcing the plan limit (Req 10.1, 10.6-10.8)."""
    service = RuleService(scope)
    rule = await service.create_rule(
        name=payload.name,
        nodes=_nodes_payload(payload.nodes),
        edges=_edges_payload(payload.edges),
        enabled=payload.enabled,
        template_id=payload.template_id,
    )
    return RuleResponse(rule=_rule_out(rule))


@router.post("/from-template", response_model=RuleResponse, status_code=201)
async def create_rule_from_template(
    payload: RuleFromTemplateRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> RuleResponse:
    """Create a Rule pre-populated from a template (Req 10.5, 11).

    Enforces the per-plan active-rule limit (Req 10.6-10.8) via the rule
    service. Declared before ``/{rule_id}`` so the literal path is not captured
    as a rule id.
    """
    service = TemplateService(scope)
    rule = await service.create_rule_from_template(payload.template_id)
    return RuleResponse(rule=_rule_out(rule))


@router.get("/{rule_id}", response_model=RuleDetailResponse)
async def get_rule(
    rule_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> RuleDetailResponse:
    """Fetch a rule and its graph (tenant-scoped, Req 3.3)."""
    service = RuleService(scope)
    rule = await service.get_rule(rule_id)
    nodes, edges = await service.get_graph(rule_id)
    return RuleDetailResponse(
        rule=_rule_out(rule),
        nodes=[_node_out(n) for n in nodes],
        edges=[_edge_out(e) for e in edges],
    )


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    payload: UpdateRuleRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> RuleResponse:
    """Update a rule (enable/disable, rename, replace graph); re-checks plan limit (Req 10.6-10.8)."""
    fields_set = payload.model_fields_set
    service = RuleService(scope)
    rule = await service.update_rule(
        rule_id,
        name=payload.name,
        enabled=payload.enabled,
        nodes=_nodes_payload(payload.nodes) if payload.nodes is not None else None,
        edges=_edges_payload(payload.edges) if payload.edges is not None else None,
        name_set="name" in fields_set,
        nodes_set="nodes" in fields_set,
        edges_set="edges" in fields_set,
    )
    return RuleResponse(rule=_rule_out(rule))


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_rule(
    rule_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Delete a rule and its graph (Req 10.1)."""
    service = RuleService(scope)
    await service.delete_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
