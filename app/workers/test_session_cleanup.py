"""Unit tests for the Session_Cleanup worker (Task 6.5, Req 30.1, 30.2).

These exercise the core sweep with ``fakeredis`` (no live Redis), covering:

- expired/orphaned session keys (no TTL) are removed (Req 30.2)
- still-valid sessions (with a remaining TTL) are preserved
- already-evicted keys are a no-op
- only the ``refresh:{jti}`` namespace is touched (other keys are left alone)
- the count of removed sessions is reported
"""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from app.core import redis_keys as rk
from app.workers import session_cleanup as sc


def _redis() -> "fakeredis.aioredis.FakeRedis":
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_removes_orphaned_session_without_ttl():
    """A refresh key with no expiry guard is treated as expired and removed."""
    redis = _redis()
    key = rk.refresh_token_key("orphan-jti")
    await redis.set(key, "user-1")  # no TTL => orphaned session

    removed = await sc.cleanup_expired_sessions(redis)

    assert removed == 1
    assert await redis.exists(key) == 0


@pytest.mark.asyncio
async def test_preserves_session_with_remaining_ttl():
    """A session that has not yet expired (TTL > 0) is kept."""
    redis = _redis()
    key = rk.refresh_token_key("live-jti")
    await redis.set(key, "user-2", ex=3600)

    removed = await sc.cleanup_expired_sessions(redis)

    assert removed == 0
    assert await redis.exists(key) == 1


@pytest.mark.asyncio
async def test_evicted_key_is_noop():
    """Keys Redis already evicted contribute nothing to the removal count."""
    redis = _redis()
    # Nothing stored; the keyspace is empty.
    removed = await sc.cleanup_expired_sessions(redis)
    assert removed == 0


@pytest.mark.asyncio
async def test_only_touches_refresh_namespace():
    """Non-session keys without a TTL must never be deleted by the sweep."""
    redis = _redis()
    orphan = rk.refresh_token_key("orphan-jti")
    other = rk.quota_key("org-1", "202401")
    await redis.set(orphan, "user-1")  # orphaned session, no TTL
    await redis.set(other, "5")  # unrelated key, also no TTL

    removed = await sc.cleanup_expired_sessions(redis)

    assert removed == 1
    assert await redis.exists(orphan) == 0
    assert await redis.exists(other) == 1


@pytest.mark.asyncio
async def test_mixed_keyspace_removes_only_expired():
    """Across many keys only the TTL-less refresh records are removed."""
    redis = _redis()
    orphans = [rk.refresh_token_key(f"orphan-{i}") for i in range(5)]
    live = [rk.refresh_token_key(f"live-{i}") for i in range(3)]
    for k in orphans:
        await redis.set(k, "u")
    for k in live:
        await redis.set(k, "u", ex=3600)

    removed = await sc.cleanup_expired_sessions(redis, scan_count=2)

    assert removed == len(orphans)
    for k in orphans:
        assert await redis.exists(k) == 0
    for k in live:
        assert await redis.exists(k) == 1


@pytest.mark.asyncio
async def test_run_stops_on_event_after_one_sweep():
    """The run loop performs a sweep and exits promptly when stopped."""
    redis = _redis()
    key = rk.refresh_token_key("orphan-jti")
    await redis.set(key, "user-1")

    stop_event = asyncio.Event()

    async def _stop_soon() -> None:
        # Allow the first sweep to complete, then request shutdown.
        await asyncio.sleep(0.01)
        stop_event.set()

    await asyncio.gather(
        sc.run(redis, stop_event, interval_seconds=0.01),
        _stop_soon(),
    )

    assert await redis.exists(key) == 0
