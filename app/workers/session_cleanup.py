"""Session_Cleanup worker (Req 30.1, 30.2).

The Session_Cleanup worker is one of the eight background workers required by
the platform (design "Background Workers", Req 30.1). Its job is to remove
expired sessions / refresh tokens past their expiry (Req 30.2).

Sessions are refresh tokens stored server-side in Redis under
``iotaps:refresh:{jti}`` (design "JWT claims structure"; ``app.core.redis_keys``
and ``app.core.security.jwt``). When a refresh token is issued the auth service
sets a Redis TTL equal to the refresh-token lifetime, so Redis evicts the key
automatically when the session's expiry time passes (Req 30.2).

This worker is the explicit, defence-in-depth sweep that backs that invariant:

- It periodically scans the ``refresh:{jti}`` keyspace and removes any session
  record that no longer carries an expiry guard (TTL ``-1``). Such an orphaned
  key would otherwise live forever, so deleting it bounds every session's
  lifetime and guarantees expired sessions are removed even if a key was ever
  written without a TTL.
- Keys that Redis has already evicted (TTL ``-2``) are skipped, and keys with a
  remaining TTL (``>= 0``) are left untouched because they have not expired yet.

The core (`cleanup_expired_sessions`) takes the Redis client as a parameter and
is free of any global state, so it can be unit-tested with ``fakeredis`` without
a live Redis. The ``run`` loop wires it to the real client on a fixed interval
and adds graceful shutdown; ``main`` is the supervised process entry point.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any, Optional

from app.core.logging import configure_logging, get_logger
from app.core.redis_client import get_redis
from app.core.redis_keys import refresh_token_key

logger = get_logger(__name__)

# Glob matching every server-side refresh-token / session record. Derived from
# the canonical key builder so it always tracks the real namespace layout
# (``iotaps:refresh:*``) rather than hard-coding the prefix.
SESSION_KEY_PATTERN = refresh_token_key("*")

# How many keys to pull per SCAN iteration. SCAN is cursor-based and never
# blocks Redis, so a moderate count keeps the sweep cheap on large keyspaces.
SCAN_COUNT = 500

# Interval between full sweeps. Sessions are primarily expired by Redis TTL in
# real time; this sweep only needs to run periodically to catch orphaned keys.
CLEANUP_INTERVAL_SECONDS = 300.0

# Redis PTTL/TTL sentinel values.
_TTL_NO_EXPIRY = -1  # key exists but has no associated expiry
_TTL_MISSING = -2  # key does not exist (already evicted)


# ---------------------------------------------------------------------------
# Core sweep (testable; no live Redis required)
# ---------------------------------------------------------------------------
async def cleanup_expired_sessions(redis: Any, *, scan_count: int = SCAN_COUNT) -> int:
    """Remove expired/orphaned session records. Returns the number deleted.

    Scans the ``refresh:{jti}`` keyspace and deletes every key that no longer
    carries an expiry guard (TTL ``-1``). Redis evicts keys automatically once
    their TTL elapses, so a refresh key without a TTL is an orphaned session
    that would never expire on its own; removing it enforces Req 30.2 (expired
    sessions are removed) as a safety net over the TTL set at issue time.

    Keys already evicted (TTL ``-2``) are ignored, and keys with a remaining
    TTL (``>= 0``) are preserved because their session is still valid.
    """
    # Collect the full set of matching keys first. Deleting keys while a SCAN
    # cursor is still in flight can cause the cursor to skip entries, so the
    # sweep is split into a non-mutating scan phase followed by deletion.
    keys: set[str] = set()
    cursor = 0
    while True:
        cursor, batch = await redis.scan(
            cursor=cursor, match=SESSION_KEY_PATTERN, count=scan_count
        )
        keys.update(batch)
        if cursor == 0:
            break

    deleted = 0
    for key in keys:
        ttl = await redis.ttl(key)
        if ttl == _TTL_NO_EXPIRY:
            # Orphaned session with no expiry guard -> remove it.
            removed = await redis.delete(key)
            deleted += int(removed)

    if deleted:
        logger.info("session_cleanup_removed", extra={"removed": deleted})
    return deleted


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
async def run(
    redis: Any,
    stop_event: Optional[asyncio.Event] = None,
    *,
    interval_seconds: float = CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Run the cleanup sweep on a fixed interval until ``stop_event`` is set."""
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        try:
            await cleanup_expired_sessions(redis)
        except Exception:  # pragma: no cover - keep the worker alive on errors
            logger.exception("session_cleanup_failed")
        await _sleep_or_stop(stop_event, interval_seconds)


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def main() -> None:
    """Process entry point (``python -m app.workers.session_cleanup``)."""
    configure_logging()
    logger.info("session_cleanup_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        redis = get_redis()
        if redis is None:  # pragma: no cover - defensive; redis lib should be present
            raise RuntimeError("Redis client unavailable; cannot run Session_Cleanup")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # pragma: no cover - Windows lacks add_signal_handler
                pass
        await run(redis, stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:  # pragma: no cover - graceful Ctrl-C
        pass
    logger.info("session_cleanup_stopped")


if __name__ == "__main__":
    main()
