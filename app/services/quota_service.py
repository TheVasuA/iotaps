"""Message_Quota counting + monthly reset (Task 14.1, Req 15.3-15.6).

Implements the design "Message Quota Counting + Monthly Reset" algorithm:

    on telemetry message (Free plan org):
        key = f"quota:{org_id}:{year}{month}"
        n = redis.incr(key)
        redis.expireat(key, end_of_billing_month)      # auto-reset (15.6)
        if n == FREE_QUOTA (20000):                     # 15.5
            emit upgrade_prompt(org_id)
        # continue accepting telemetry regardless        (15.5)
    # command/ack/status never call this path            (15.4)

Only telemetry messages are ever counted: the MQTT_Listener routes command,
ack, and status messages to handlers that never touch this module, and
:func:`count_telemetry_message` additionally guards on
``QUOTA_COUNTED_TYPES`` so a misrouted call cannot inflate the counter
(Req 15.4).

The monthly counter lives in Redis under ``quota:{org}:{yyyymm}``
(``app.core.redis_keys.quota_key``) and is given an ``expireat`` of the end of
the billing month, so when a new month begins the next ``INCR`` lands on a
fresh key that starts at 1 - the counter "resets" automatically without a
scheduled job (Req 15.6).

Pro orgs have an unlimited message allowance and are not metered
(``plan_limits.is_metered`` is False), so the quota path is skipped entirely for
them (Req 15.2). When a Free org first *reaches* its allowance an upgrade prompt
is published once (on the exact crossing), while the message is still accepted
and counted (Req 15.5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.core import redis_keys as rk
from app.core.logging import get_logger
from app.core.mqtt_topics import QUOTA_COUNTED_TYPES, MessageType
from app.services.plan_limits import is_metered, limits_for_plan

logger = get_logger(__name__)


@dataclass(frozen=True)
class QuotaResult:
    """Outcome of counting one telemetry message against an org's quota.

    ``counted`` is False when the plan is unmetered (Pro) and the message did
    not touch the counter. ``count`` is the new monthly total after the
    increment (0 when not counted). ``limit`` is the plan's monthly allowance
    (None = unlimited). ``upgrade_prompt`` is True only on the single message
    that takes the org *to* its allowance, so the prompt is emitted exactly once
    per billing month (Req 15.5).
    """

    counted: bool
    count: int
    limit: Optional[int]
    upgrade_prompt: bool


def end_of_billing_month(now: datetime) -> datetime:
    """Return the first instant of the *next* calendar month (UTC).

    Used as the quota key's ``expireat`` so the counter expires exactly when the
    billing month rolls over and the next month's first message starts a fresh
    count (Req 15.6). The boundary is exclusive (start of next month) which is
    the natural TTL expiry point.
    """
    aware = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    aware = aware.astimezone(timezone.utc)
    if aware.month == 12:
        return datetime(aware.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(aware.year, aware.month + 1, 1, tzinfo=timezone.utc)


async def count_telemetry_message(
    redis: Any,
    org_id: str,
    plan: Optional[str],
    *,
    message_type: MessageType = MessageType.TELEMETRY,
    now: Optional[datetime] = None,
) -> QuotaResult:
    """Count one telemetry message against the org's monthly Message_Quota.

    Increments ``quota:{org}:{yyyymm}`` and refreshes its month-end expiry, then
    reports whether the org has just reached its allowance (Req 15.3, 15.5,
    15.6). Telemetry is always accepted; this function never blocks ingestion -
    it only counts and signals.

    No-ops (returning ``counted=False``) when:
      - ``message_type`` is not a quota-counted type (command/ack/status,
        Req 15.4), or
      - the plan is unmetered (Pro has an unlimited allowance, Req 15.2).
    """
    # Only telemetry is ever counted; command/ack/status are excluded (Req 15.4).
    if message_type not in QUOTA_COUNTED_TYPES:
        return QuotaResult(counted=False, count=0, limit=None, upgrade_prompt=False)

    limit = limits_for_plan(plan).max_messages_per_month
    if not is_metered(plan):
        # Pro / unlimited: telemetry is accepted but never metered (Req 15.2).
        return QuotaResult(counted=False, count=0, limit=limit, upgrade_prompt=False)

    now = now or datetime.now(timezone.utc)
    key = rk.quota_key(org_id, now)

    count = int(await redis.incr(key))
    # Refresh the month-end expiry on every increment so the counter resets when
    # the billing month rolls over (Req 15.6). expireat takes a unix timestamp.
    try:
        await redis.expireat(key, int(end_of_billing_month(now).timestamp()))
    except Exception:  # pragma: no cover - expiry is best-effort, never blocks ingest
        logger.warning("quota_expireat_failed", extra={"org_id": org_id})

    # Emit the upgrade prompt exactly on the crossing to the allowance (Req 15.5).
    upgrade_prompt = limit is not None and count == limit
    if upgrade_prompt:
        await _emit_upgrade_prompt(redis, org_id, count=count, limit=limit)

    return QuotaResult(
        counted=True, count=count, limit=limit, upgrade_prompt=upgrade_prompt
    )


# Seconds to cache an org's plan in Redis so the listener avoids a Postgres
# read per telemetry message. Short enough that an upgrade/downgrade takes
# effect quickly; quota correctness does not depend on freshness within a month.
_ORG_PLAN_CACHE_TTL_SECONDS = 300


async def resolve_org_plan(redis: Any, org_id: str) -> Optional[str]:
    """Return an org's subscription plan, using a Redis read-through cache.

    The MQTT_Listener calls this for every telemetry message, so it must be
    cheap and must never raise: on a cache miss it loads the plan from Postgres
    and populates the cache; if the DB is unreachable it returns ``None`` (which
    the metering logic treats as the conservative Free/metered default per
    Req 15.7) so ingestion is never blocked by quota bookkeeping.
    """
    cache_key = rk.org_plan_key(org_id)
    try:
        cached = await redis.get(cache_key)
    except Exception:  # pragma: no cover - cache must not break ingest
        cached = None
    if cached is not None:
        return cached or None

    plan = await _load_org_plan_from_db(org_id)
    if plan is not None:
        try:
            await redis.set(cache_key, plan, ex=_ORG_PLAN_CACHE_TTL_SECONDS)
        except Exception:  # pragma: no cover - cache population is best-effort
            logger.warning("org_plan_cache_write_failed", extra={"org_id": org_id})
    return plan


async def _load_org_plan_from_db(org_id: str) -> Optional[str]:
    """Load one org's plan from Postgres, returning ``None`` on any failure."""
    try:
        import uuid as _uuid

        from sqlalchemy import select

        from app.db.session import async_session_factory
        from app.models.organization import Organization

        try:
            pk: Any = _uuid.UUID(str(org_id))
        except (ValueError, TypeError):
            pk = org_id

        async with async_session_factory() as session:
            result = await session.execute(
                select(Organization.plan).where(Organization.id == pk)
            )
            row = result.first()
            return row[0] if row is not None else None
    except Exception:  # pragma: no cover - DB unavailability must not block ingest
        logger.warning("org_plan_db_load_failed", extra={"org_id": org_id})
        return None


async def _emit_upgrade_prompt(
    redis: Any, org_id: str, *, count: int, limit: int
) -> None:
    """Publish a one-shot upgrade prompt for an org that hit its quota (Req 15.5).

    Failure to publish must never interrupt telemetry ingestion, so any error is
    logged and swallowed.
    """
    message = json.dumps(
        {
            "type": "upgrade_prompt",
            "org_id": org_id,
            "reason": "message_quota_reached",
            "count": count,
            "limit": limit,
        }
    )
    try:
        await redis.publish(rk.upgrade_prompt_channel(org_id), message)
        logger.info(
            "message_quota_reached",
            extra={"org_id": org_id, "count": count, "limit": limit},
        )
    except Exception:  # pragma: no cover - prompt is best-effort
        logger.warning("upgrade_prompt_publish_failed", extra={"org_id": org_id})
