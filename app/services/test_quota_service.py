"""Unit tests for Message_Quota counting + monthly reset (Task 14.1, Req 15.3-15.6).

Exercises the quota counter against ``fakeredis`` (no live Redis/Postgres):

  - telemetry increments the monthly counter; command/ack/status never do (15.4)
  - Pro/unmetered plans are not counted (15.2)
  - the upgrade prompt fires exactly once, on reaching the allowance, and
    telemetry keeps being accepted/counted afterwards (15.5)
  - the counter key carries a month-end expiry and a new month starts fresh (15.6)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

from app.core import redis_keys as rk
from app.core.mqtt_topics import MessageType
from app.services import quota_service as qs


def _redis() -> "fakeredis.aioredis.FakeRedis":
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# Use real wall-clock months so the Redis ``expireat`` (end of the billing
# month) always lands in the future - otherwise Redis would expire the key
# immediately. ``NOW`` is this month; ``NEXT_MONTH`` is the first instant of the
# following month (a distinct quota-key period).
NOW = datetime.now(timezone.utc)
NEXT_MONTH = qs.end_of_billing_month(NOW)


# ---------------------------------------------------------------------------
# Counting telemetry (Req 15.3)
# ---------------------------------------------------------------------------
async def test_telemetry_increments_monthly_counter():
    redis = _redis()
    r1 = await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    r2 = await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)

    assert (r1.counted, r1.count) == (True, 1)
    assert (r2.counted, r2.count) == (True, 2)
    assert await redis.get(rk.quota_key("org-1", NOW)) == "2"


# ---------------------------------------------------------------------------
# Excluded message types never count (Req 15.4)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mtype", [MessageType.COMMAND, MessageType.ACK, MessageType.STATUS]
)
async def test_command_ack_status_never_counted(mtype):
    redis = _redis()
    result = await qs.count_telemetry_message(
        redis, "org-1", "free", message_type=mtype, now=NOW
    )
    assert result.counted is False
    assert await redis.get(rk.quota_key("org-1", NOW)) is None


# ---------------------------------------------------------------------------
# Pro / unmetered plans are not counted (Req 15.2)
# ---------------------------------------------------------------------------
async def test_pro_plan_is_not_metered():
    redis = _redis()
    result = await qs.count_telemetry_message(redis, "org-1", "pro", now=NOW)
    assert result.counted is False
    assert result.limit is None
    assert await redis.get(rk.quota_key("org-1", NOW)) is None


async def test_ambiguous_plan_falls_back_to_metered_free():
    redis = _redis()
    # An unrecognised plan must be metered like Free (Req 15.7).
    result = await qs.count_telemetry_message(redis, "org-1", "mystery", now=NOW)
    assert result.counted is True
    assert result.limit == 20000


# ---------------------------------------------------------------------------
# Upgrade prompt on reaching the allowance (Req 15.5)
# ---------------------------------------------------------------------------
async def test_upgrade_prompt_fires_once_on_reaching_limit():
    redis = _redis()
    # Pre-seed the counter just below the Free allowance.
    await redis.set(rk.quota_key("org-1", NOW), "19998")

    pubsub = redis.pubsub()
    await pubsub.subscribe(rk.upgrade_prompt_channel("org-1"))
    await pubsub.get_message(timeout=0.1)  # drop the subscribe confirmation

    # 19999: not yet at the allowance.
    r1 = await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    assert (r1.count, r1.upgrade_prompt) == (19999, False)

    # 20000: reaches the allowance -> prompt fires, telemetry still accepted.
    r2 = await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    assert (r2.count, r2.counted, r2.upgrade_prompt) == (20000, True, True)

    # 20001: over the allowance -> telemetry still counted, no second prompt.
    r3 = await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    assert (r3.count, r3.counted, r3.upgrade_prompt) == (20001, True, False)

    # Exactly one upgrade-prompt message was published.
    prompts = []
    while True:
        msg = await pubsub.get_message(timeout=0.1)
        if msg is None:
            break
        if msg.get("type") == "message":
            prompts.append(json.loads(msg["data"]))
    assert len(prompts) == 1
    assert prompts[0]["type"] == "upgrade_prompt"
    assert prompts[0]["org_id"] == "org-1"
    assert prompts[0]["limit"] == 20000


# ---------------------------------------------------------------------------
# Monthly reset via key expiry (Req 15.6)
# ---------------------------------------------------------------------------
async def test_counter_has_month_end_expiry():
    redis = _redis()
    await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    ttl = await redis.ttl(rk.quota_key("org-1", NOW))
    # A positive TTL means the key will auto-expire (reset) at month end.
    assert ttl > 0


async def test_new_month_starts_fresh_count():
    redis = _redis()
    await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)
    await qs.count_telemetry_message(redis, "org-1", "free", now=NOW)

    # A new billing month uses a different key, so the count starts at 1 again.
    nxt = await qs.count_telemetry_message(redis, "org-1", "free", now=NEXT_MONTH)
    assert nxt.count == 1
    assert rk.quota_key("org-1", NOW) != rk.quota_key("org-1", NEXT_MONTH)


def test_end_of_billing_month_rolls_to_next_month():
    jan = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert qs.end_of_billing_month(jan) == datetime(2025, 2, 1, tzinfo=timezone.utc)
    # December rolls over the year boundary.
    dec = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    assert qs.end_of_billing_month(dec) == datetime(2026, 1, 1, tzinfo=timezone.utc)
