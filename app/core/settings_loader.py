"""Read-through loader for dynamic platform settings (Req 29.4).

The Super_Admin can change platform-wide settings (pricing, plan limits, JWT
expiry, rate limits, 2FA policy, themes) at runtime. Those live in the
`platform_settings` table (`key TEXT PK, value JSONB`) and must apply
platform-wide immediately upon write.

This loader implements a Redis-backed read-through cache:

  get(key) -> read Redis cache -> on miss, read the source of truth ->
              populate cache (with TTL) -> return value.

  set(key, value) -> write the source of truth -> invalidate/refresh the cache
              so every stateless app server picks up the change immediately.

Task 1.3 provisions the `platform_settings` table and wires the real database
source. Until then a thin in-memory store with sensible defaults stands in as
the source of truth so the API boots and behaves correctly. The cache contract
(Redis read-through + invalidation) is final and does not change when the DB is
wired in - only `_DbSettingsSource` gains a real implementation.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

# Redis key namespace for cached platform settings.
_CACHE_PREFIX = "platform_settings:"

# Built-in defaults applied platform-wide until the Super_Admin overrides them.
# These mirror the plan/pricing/JWT values described in the design so other
# modules have a single source to read from.
_DEFAULT_SETTINGS: dict[str, Any] = {
    "pricing_tiers_monthly": [
        {"min": 1, "max": 10, "unit_price": 99},
        {"min": 11, "max": 50, "unit_price": 79},
        {"min": 51, "max": 200, "unit_price": 69},
        {"min": 201, "max": None, "unit_price": 59},
    ],
    "annual_unit_price": 948,
    "plan_limits": {
        "free": {
            "devices": 2,
            "messages_per_month": 20000,
            "retention_days": 7,
            "sensors": 10,
            "rules": 2,
        },
        "pro": {
            "devices": None,
            "messages_per_month": None,
            "retention_days": 90,
            "sensors": 20,
            "rules": None,
        },
    },
    "jwt_access_ttl_seconds": 900,
    "jwt_refresh_ttl_seconds": 2592000,
    "rate_limits": {"per_ip_per_min": 120, "per_org_per_min": 600},
    "twofa_required": False,
    "commission_default": 50,
    "refund_window_days": 14,
}


class _DbSettingsSource:
    """Source-of-truth backing store for platform settings.

    Placeholder in-memory implementation seeded with defaults. Task 1.3 replaces
    the body of these methods with `platform_settings` table reads/writes; the
    method signatures are stable so callers and the cache layer are unaffected.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = dict(_DEFAULT_SETTINGS)

    async def read(self, key: str) -> Any | None:
        return self._store.get(key)

    async def read_all(self) -> dict[str, Any]:
        return dict(self._store)

    async def write(self, key: str, value: Any) -> None:
        self._store[key] = value


# Single shared source instance (process-local until backed by the DB).
_source = _DbSettingsSource()


async def get_setting(key: str, default: Any | None = None) -> Any | None:
    """Return a platform setting, using the Redis read-through cache.

    Falls back to the source of truth on cache miss/unavailability, then to the
    provided ``default`` (or the built-in default) if the key is unknown.
    """
    redis = get_redis()
    cache_key = _CACHE_PREFIX + key

    # 1. Try the cache.
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached is not None:
                return json.loads(cached)
        except Exception:  # pragma: no cover - cache must never break reads
            logger.warning("platform_settings_cache_read_failed", extra={"key": key})

    # 2. Cache miss -> read source of truth.
    value = await _source.read(key)
    if value is None:
        return default if default is not None else _DEFAULT_SETTINGS.get(key)

    # 3. Populate the cache for subsequent reads.
    if redis is not None:
        ttl = get_settings().platform_settings_cache_ttl_seconds
        try:
            await redis.set(cache_key, json.dumps(value), ex=ttl)
        except Exception:  # pragma: no cover - cache population is best-effort
            logger.warning("platform_settings_cache_write_failed", extra={"key": key})

    return value


async def set_setting(key: str, value: Any) -> None:
    """Persist a platform setting and refresh the cache immediately (Req 29.4).

    Writing to the source of truth first, then refreshing the cache, ensures
    every stateless app server observes the new value platform-wide as soon as
    its cache entry is refreshed or expires.
    """
    await _source.write(key, value)

    redis = get_redis()
    if redis is not None:
        cache_key = _CACHE_PREFIX + key
        ttl = get_settings().platform_settings_cache_ttl_seconds
        try:
            await redis.set(cache_key, json.dumps(value), ex=ttl)
        except Exception:  # pragma: no cover - cache refresh is best-effort
            logger.warning("platform_settings_cache_refresh_failed", extra={"key": key})


async def get_all_settings() -> dict[str, Any]:
    """Return all platform settings from the source of truth."""
    return await _source.read_all()
