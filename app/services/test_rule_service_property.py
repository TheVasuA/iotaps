"""Property-based test for active-rule plan limits (Task 10.2, Req 10).

# Feature: iotaps-platform, Property 9: Active rule plan limits

Property 9 (design.md "Correctness Properties"):

    For any sequence of rule-creation requests, an Organization on the
    Free_Plan or with an ambiguous plan never has more than 2 active Rules,
    while an Organization on the Pro_Plan may have any number.

Validates: Requirements 10.6, 10.7, 10.8

Drives the real :class:`app.services.rule_service.RuleService` against an
in-memory SQLite database (no live Postgres/Redis/MQTT). Each Hypothesis
example generates a plan value (Free, Pro, or an ambiguous/unknown value) and a
sequence of operations that try to grow the org's active-rule set:

    - ``create_enabled``  : create a new rule that starts active
    - ``create_disabled`` : create a new rule that starts inactive
    - ``enable``          : re-enable a previously-created disabled rule

Operations that would exceed a Free/ambiguous org's allowance raise
``PlanLimitError`` and are swallowed (the platform rejects them). After every
operation - and again at the end - we assert the invariant directly from the DB:

    - Free / ambiguous plan: active (enabled) rule count is always <= 2 (10.6,
      10.8).
    - Pro plan: no ``PlanLimitError`` is ever raised; the count may exceed 2
      (10.7).
"""

from __future__ import annotations

import asyncio
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import JSON, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.security.principal import ROLE_PROJECT_CENTER, Principal
from app.core.security.tenant import TenantScope
from app.db.base import Base
from app.models.organization import Organization
from app.models.rule import Rule, RuleEdge, RuleNode
from app.services.rule_service import (
    FREE_PLAN_ACTIVE_RULE_LIMIT,
    PRO_PLAN,
    PlanLimitError,
    RuleService,
    plan_active_rule_limit,
)

# Tables required for this property (the full metadata pulls in Postgres-only
# DDL from unrelated models).
_TABLES = [
    Organization.__table__,
    Rule.__table__,
    RuleNode.__table__,
    RuleEdge.__table__,
]

# Plan values exercised. "pro" variants must resolve to unlimited; everything
# else (free, unknown, empty, None) must fall back to the Free limit (10.8).
_PRO_PLANS = ["pro", "Pro", " pro ", "PRO"]
_FREE_OR_AMBIGUOUS_PLANS = ["free", "Free", "", "   ", "enterprise", "trial", "??", None]


def _prepare_tables() -> None:
    """Adapt Postgres-only DDL so the tables compile on the SQLite test engine."""
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())
    # JSONB -> JSON for SQLite-backed tests.
    RuleNode.__table__.c.config.type = JSON()
    RuleNode.__table__.c.position.type = JSON()
    # ``enabled`` has a Postgres server_default; give SQLite a python default.
    Rule.__table__.c.enabled.server_default = None
    Rule.__table__.c.enabled.default = ColumnDefault(True)


def _make_engine():
    _prepare_tables()
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _scope(session: AsyncSession, org_id: uuid.UUID) -> TenantScope:
    principal = Principal(
        user_id=str(uuid.uuid4()), org_id=str(org_id), role=ROLE_PROJECT_CENTER
    )
    return TenantScope(principal, session)


# ---------------------------------------------------------------------------
# Generators: a plan + a sequence of "grow the active set" operations.
# ---------------------------------------------------------------------------
_operation = st.sampled_from(["create_enabled", "create_disabled", "enable"])
_operations = st.lists(_operation, min_size=0, max_size=25)


async def _active_count(session: AsyncSession, org_id: uuid.UUID) -> int:
    """Count active (enabled) rules in ``org_id`` straight from the DB."""
    result = await session.execute(
        select(func.count())
        .select_from(Rule)
        .where(Rule.org_id == org_id, Rule.enabled.is_(True))
    )
    return int(result.scalar_one())


async def _run(plan: str | None, operations: list[str]) -> None:
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    limit = plan_active_rule_limit(plan)
    is_pro = limit is None

    try:
        async with factory() as session:
            org = Organization(name="Org", type="project_center", plan=plan)
            session.add(org)
            await session.flush()
            org_id = org.id
            await session.commit()

            service = RuleService(_scope(session, org_id))
            disabled_rule_ids: list[uuid.UUID] = []
            counter = 0
            pro_enabled_total = 0  # expected active count for a Pro org

            for op in operations:
                counter += 1
                try:
                    if op == "create_enabled":
                        await service.create_rule(name=f"r{counter}", enabled=True)
                        # Created active rules count against the limit.
                        pro_enabled_total += 1
                    elif op == "create_disabled":
                        rule = await service.create_rule(
                            name=f"r{counter}", enabled=False
                        )
                        disabled_rule_ids.append(rule.id)
                    else:  # enable a previously-disabled rule, if any
                        if not disabled_rule_ids:
                            continue
                        target = disabled_rule_ids.pop()
                        await service.update_rule(target, enabled=True)
                        pro_enabled_total += 1
                except PlanLimitError:
                    # The platform rejected an operation that would exceed the
                    # allowance. A Pro org must never be limited (10.7).
                    assert not is_pro, "Pro_Plan org was incorrectly limited"

                # Invariant after every operation: a Free/ambiguous org never
                # holds more than the Free limit of active rules (10.6, 10.8).
                active = await _active_count(session, org_id)
                if not is_pro:
                    assert active <= limit, (
                        f"plan={plan!r}: active rule count {active} "
                        f"exceeded limit {limit}"
                    )

            # Final invariant straight from the DB.
            final_active = await _active_count(session, org_id)
            if is_pro:
                # Pro is unlimited: every activating request must have succeeded
                # (no PlanLimitError), so the active count equals the number of
                # activations performed - in particular it can exceed the Free
                # cap (10.7).
                assert final_active == pro_enabled_total
            else:
                assert final_active <= limit
    finally:
        await engine.dispose()


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    plan=st.one_of(
        st.sampled_from(_FREE_OR_AMBIGUOUS_PLANS),
        st.sampled_from(_PRO_PLANS),
    ),
    operations=_operations,
)
def test_active_rule_plan_limits(plan: str | None, operations: list[str]) -> None:
    """Property 9: active rule plan limits.

    Validates: Requirements 10.6, 10.7, 10.8
    """
    asyncio.run(_run(plan, operations))


def test_plan_limit_resolution_examples() -> None:
    """Unit anchors for the plan-limit resolution (10.6, 10.7, 10.8)."""
    # Free / ambiguous -> the Free cap of 2 (10.6, 10.8).
    for plan in ["free", "Free", "", "   ", "enterprise", None]:
        assert plan_active_rule_limit(plan) == FREE_PLAN_ACTIVE_RULE_LIMIT
    # Pro (case/whitespace tolerant) -> unlimited (10.7).
    for plan in ["pro", "Pro", " pro ", PRO_PLAN]:
        assert plan_active_rule_limit(plan) is None
