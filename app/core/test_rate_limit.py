"""Unit tests for the Redis token-bucket rate limiter (Task 2.5, design stage 1).

Covers the algorithm in ``app.core.rate_limit``:
  - a fresh bucket allows up to ``capacity`` requests, then rejects (429 source)
  - rejection reports a positive ``retry_after`` hint
  - tokens refill over time at ``refill_rate``
  - per-IP and per-org buckets are independent (keyed separately)
  - fails open when Redis is unavailable

A fake in-memory Redis (fakeredis) backs the buckets - no live Redis.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.core.rate_limit import (
    RateLimitPolicy,
    check_rate_limit,
)
from app.core.redis_keys import rate_limit_ip_key, rate_limit_org_key


def _fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def test_allows_up_to_capacity_then_rejects():
    redis = _fake_redis()
    policy = RateLimitPolicy(capacity=3, refill_rate=0.0)  # no refill
    key = rate_limit_ip_key("1.2.3.4")

    # First 3 requests consume the bucket.
    for _ in range(3):
        result = await check_rate_limit(redis, key, policy, now=1000.0)
        assert result.allowed is True

    # 4th request is rejected.
    blocked = await check_rate_limit(redis, key, policy, now=1000.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0


async def test_rejection_reports_retry_after():
    redis = _fake_redis()
    policy = RateLimitPolicy(capacity=1, refill_rate=1.0)  # 1 token/sec
    key = rate_limit_ip_key("5.6.7.8")

    assert (await check_rate_limit(redis, key, policy, now=2000.0)).allowed is True
    blocked = await check_rate_limit(redis, key, policy, now=2000.0)
    assert blocked.allowed is False
    # Need ~1 second to earn the next token.
    assert blocked.retry_after > 0
    assert blocked.retry_after_seconds >= 1


async def test_tokens_refill_over_time():
    redis = _fake_redis()
    policy = RateLimitPolicy(capacity=2, refill_rate=1.0)  # 1 token/sec
    key = rate_limit_ip_key("9.9.9.9")

    # Drain the bucket at t=0.
    await check_rate_limit(redis, key, policy, now=0.0)
    await check_rate_limit(redis, key, policy, now=0.0)
    assert (await check_rate_limit(redis, key, policy, now=0.0)).allowed is False

    # After 2 seconds, 2 tokens have refilled.
    assert (await check_rate_limit(redis, key, policy, now=2.0)).allowed is True
    assert (await check_rate_limit(redis, key, policy, now=2.0)).allowed is True
    assert (await check_rate_limit(redis, key, policy, now=2.0)).allowed is False


async def test_refill_capped_at_capacity():
    redis = _fake_redis()
    policy = RateLimitPolicy(capacity=2, refill_rate=1.0)
    key = rate_limit_ip_key("8.8.8.8")
    # Idle for a long time should not exceed capacity.
    await check_rate_limit(redis, key, policy, now=0.0)  # init bucket
    result = await check_rate_limit(redis, key, policy, now=10_000.0)
    assert result.allowed is True
    # Only capacity-1 should remain after consuming one (not capacity + huge).
    assert result.remaining <= policy.capacity


async def test_ip_and_org_buckets_are_independent():
    redis = _fake_redis()
    policy = RateLimitPolicy(capacity=1, refill_rate=0.0)
    ip_key = rate_limit_ip_key("1.1.1.1")
    org_key = rate_limit_org_key("orgA")

    assert (await check_rate_limit(redis, ip_key, policy, now=1.0)).allowed is True
    # Org bucket is untouched by the IP consumption.
    assert (await check_rate_limit(redis, org_key, policy, now=1.0)).allowed is True
    # Each is now exhausted independently.
    assert (await check_rate_limit(redis, ip_key, policy, now=1.0)).allowed is False
    assert (await check_rate_limit(redis, org_key, policy, now=1.0)).allowed is False


async def test_fails_open_without_redis():
    policy = RateLimitPolicy(capacity=1, refill_rate=0.0)
    result = await check_rate_limit(None, rate_limit_ip_key("x"), policy)
    assert result.allowed is True
