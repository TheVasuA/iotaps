"""Redis client accessor.

Provides a lazily-created async Redis client shared across the app. Full Redis
key namespacing (ingest queue, pub/sub, sessions, quota counters) is configured
in task 1.4; this module only establishes the connection used by the
platform-settings read-through cache for now.
"""

from __future__ import annotations

from typing import Optional

try:  # redis-py provides asyncio support under redis.asyncio
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - redis may be absent in minimal envs
    Redis = None  # type: ignore[assignment]

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: "Optional[Redis]" = None


def get_redis() -> "Optional[Redis]":
    """Return the shared async Redis client, or None if unavailable.

    The client is created lazily on first use. If the ``redis`` package is not
    installed the function returns ``None`` so callers can degrade gracefully
    (e.g. the settings loader falls back to defaults).
    """
    global _client
    if Redis is None:
        return None
    if _client is None:
        settings = get_settings()
        try:
            _client = Redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        except Exception:  # pragma: no cover - defensive
            logger.warning("redis_client_init_failed")
            return None
    return _client


async def close_redis() -> None:
    """Close the shared Redis client on application shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # pragma: no cover - defensive
            logger.warning("redis_client_close_failed")
        finally:
            _client = None
