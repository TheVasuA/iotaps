"""Rule persistence and plan-limit enforcement (Task 10.1, Req 10).

Encapsulates the business logic behind the Rules API (design.md
"Rules & Templates"):

    - list rules in the caller's org
    - create a rule from a React Flow graph (nodes + edges), enforcing the
      per-plan active-rule limit
    - fetch a single rule with its graph
    - patch a rule (enable/disable, replace nodes/edges), re-checking the limit
      when a rule is being (re)enabled
    - delete a rule (cascades to its nodes/edges)

The service is transport-agnostic: it takes a :class:`TenantScope` (carrying the
principal + DB session and enforcing tenant isolation) and raw values, and
returns ORM objects. The HTTP router (``app.api.v1.rules``) maps these to
request/response schemas.

Plan limit (Req 10.6-10.8):
  - Free_Plan or an *ambiguous* plan: at most 2 active (``enabled``) rules.
  - Pro_Plan: unlimited active rules.
  - "Ambiguous" means any plan value that is not recognised as Pro (e.g. None,
    empty, or an unexpected string) - we fail safe to the Free limit (Req 10.8).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ValidationError
from app.core.security.tenant import TenantScope
from app.models.organization import Organization
from app.models.rule import Rule, RuleEdge, RuleNode

# Maximum active rules permitted on the Free plan (and any ambiguous plan).
FREE_PLAN_ACTIVE_RULE_LIMIT = 2

# Canonical plan value that grants an unlimited active-rule allowance.
PRO_PLAN = "pro"


class PlanLimitError(AppError):
    """Raised when an action would exceed the org's active-rule allowance."""

    error_code = "plan_limit_exceeded"
    status_code = 403


def plan_active_rule_limit(plan: str | None) -> int | None:
    """Return the active-rule limit for ``plan``.

    Returns ``None`` for an unlimited allowance (Pro_Plan, Req 10.7), or the
    Free-plan integer limit for Free or any ambiguous/unknown plan (Req 10.6,
    10.8). Normalises case/whitespace so "Pro"/" pro " resolve to Pro.
    """
    normalized = (plan or "").strip().lower()
    if normalized == PRO_PLAN:
        return None
    return FREE_PLAN_ACTIVE_RULE_LIMIT


class RuleService:
    """Tenant-scoped CRUD over rules and their React Flow graphs."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session

    @property
    def _org_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.org_id))

    # ------------------------------------------------------------------
    # Plan limit helpers (Req 10.6-10.8)
    # ------------------------------------------------------------------
    async def _org_plan(self) -> str | None:
        """Fetch the caller's organization plan value (may be ambiguous)."""
        org = await self._session.get(Organization, self._org_uuid)
        return org.plan if org is not None else None

    async def _count_active_rules(self, *, exclude_id: uuid.UUID | None = None) -> int:
        """Count active (enabled) rules in the caller's org."""
        stmt = (
            select(func.count())
            .select_from(Rule)
            .where(Rule.org_id == self._org_uuid, Rule.enabled.is_(True))
        )
        if exclude_id is not None:
            stmt = stmt.where(Rule.id != exclude_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def _enforce_active_limit(self, *, exclude_id: uuid.UUID | None = None) -> None:
        """Raise :class:`PlanLimitError` if adding one active rule exceeds the limit.

        Pro orgs (limit ``None``) are always permitted. For Free/ambiguous orgs,
        the count of currently active rules (excluding ``exclude_id`` when a rule
        is being updated in place) must be below the limit before activating one
        more.
        """
        limit = plan_active_rule_limit(await self._org_plan())
        if limit is None:
            return
        active = await self._count_active_rules(exclude_id=exclude_id)
        if active >= limit:
            raise PlanLimitError(
                f"Your plan allows at most {limit} active rules. "
                "Disable an existing rule or upgrade to Pro.",
            )

    # ------------------------------------------------------------------
    # Graph persistence helpers
    # ------------------------------------------------------------------
    async def _flush_graph(
        self,
        rule: Rule,
        nodes: list[dict] | None,
        edges: list[dict] | None,
    ) -> None:
        """Create node rows, flush to obtain ids, then create edge rows."""
        nodes = nodes or []
        edges = edges or []

        client_to_db: dict[str, RuleNode] = {}
        for node in nodes:
            if "node_type" not in node:
                raise ValidationError(
                    "Each rule node requires a node_type",
                    error_code="invalid_rule_graph",
                )
            db_node = RuleNode(
                org_id=self._org_uuid,
                rule_id=rule.id,
                node_type=node["node_type"],
                config=node.get("config"),
                position=node.get("position"),
            )
            self._session.add(db_node)
            client_id = node.get("id")
            if client_id is not None:
                client_to_db[str(client_id)] = db_node

        # Obtain generated node ids before wiring edges.
        await self._session.flush()

        for edge in edges:
            from_key = str(edge.get("from")) if edge.get("from") is not None else None
            to_key = str(edge.get("to")) if edge.get("to") is not None else None
            from_node = client_to_db.get(from_key) if from_key else None
            to_node = client_to_db.get(to_key) if to_key else None
            if from_node is None or to_node is None:
                raise ValidationError(
                    "Rule edge references an unknown node",
                    error_code="invalid_rule_graph",
                )
            self._session.add(
                RuleEdge(
                    org_id=self._org_uuid,
                    rule_id=rule.id,
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                )
            )

    async def _delete_graph(self, rule_id: uuid.UUID) -> None:
        """Remove all nodes/edges for a rule (used when replacing the graph)."""
        edges = await self._session.execute(
            select(RuleEdge).where(RuleEdge.rule_id == rule_id)
        )
        for edge in edges.scalars():
            await self._session.delete(edge)
        # Flush edge deletes before deleting nodes (FK from_node/to_node).
        await self._session.flush()
        nodes = await self._session.execute(
            select(RuleNode).where(RuleNode.rule_id == rule_id)
        )
        for node in nodes.scalars():
            await self._session.delete(node)
        await self._session.flush()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def list_rules(self) -> list[Rule]:
        """List rules in the caller's org (Req 3.2)."""
        stmt = self._scope.select(Rule).order_by(Rule.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: uuid.UUID) -> Rule:
        """Fetch a rule by id, enforcing tenant ownership (Req 3.3)."""
        return await self._scope.get(Rule, rule_id)

    async def get_graph(
        self, rule_id: uuid.UUID
    ) -> tuple[list[RuleNode], list[RuleEdge]]:
        """Return the (nodes, edges) that make up a rule's graph."""
        await self._scope.get(Rule, rule_id)  # tenant ownership check
        nodes = await self._session.execute(
            select(RuleNode).where(RuleNode.rule_id == rule_id)
        )
        edges = await self._session.execute(
            select(RuleEdge).where(RuleEdge.rule_id == rule_id)
        )
        return list(nodes.scalars().all()), list(edges.scalars().all())

    # ------------------------------------------------------------------
    # Create (Req 10.1, 10.6-10.8)
    # ------------------------------------------------------------------
    async def create_rule(
        self,
        *,
        name: str,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        enabled: bool = True,
        template_id: uuid.UUID | None = None,
    ) -> Rule:
        """Create a rule and persist its graph, enforcing the plan limit.

        A new rule defaults to active (``enabled``). When created active, the
        per-plan active-rule limit is enforced first (Req 10.6-10.8) so a Free
        org can never end up with more than 2 active rules.
        """
        if not name or not name.strip():
            raise ValidationError(
                "Rule name is required", error_code="invalid_rule_name"
            )

        if enabled:
            await self._enforce_active_limit()

        rule = Rule(
            org_id=self._org_uuid,
            name=name.strip(),
            enabled=enabled,
            template_id=template_id,
        )
        self._session.add(rule)
        await self._session.flush()  # assign rule.id

        await self._flush_graph(rule, nodes, edges)

        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    # ------------------------------------------------------------------
    # Update (Req 10.1, 10.6-10.8)
    # ------------------------------------------------------------------
    async def update_rule(
        self,
        rule_id: uuid.UUID,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        name_set: bool = False,
        nodes_set: bool = False,
        edges_set: bool = False,
    ) -> Rule:
        """Apply a partial update to a rule.

        Enabling a currently-disabled rule re-checks the plan limit so a Free
        org cannot bypass the cap by creating rules disabled and toggling them
        on (Req 10.6-10.8). Supplying ``nodes``/``edges`` replaces the stored
        graph atomically.
        """
        rule = await self._scope.get(Rule, rule_id)

        if name_set:
            if not name or not name.strip():
                raise ValidationError(
                    "Rule name is required", error_code="invalid_rule_name"
                )
            rule.name = name.strip()

        if enabled is not None and enabled and not rule.enabled:
            # Re-enabling: ensure activating this rule stays within the limit.
            await self._enforce_active_limit(exclude_id=rule.id)
        if enabled is not None:
            rule.enabled = enabled

        if nodes_set or edges_set:
            await self._delete_graph(rule.id)
            await self._flush_graph(rule, nodes, edges)

        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        """Delete a rule and its graph (Req 10.1)."""
        rule = await self._scope.get(Rule, rule_id)
        await self._delete_graph(rule.id)
        await self._session.delete(rule)
        await self._session.commit()
