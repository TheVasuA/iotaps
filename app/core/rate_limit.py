"""Redis token-bucket rate limiting (design.md "Middleware stack", step 1).

The first stage of the middleware stack throttles abusive clients *before* any
authentication or database work happens. Limiting is applied on two axes:

- **per client IP** - blunts anonymous floods (login brute force, scraping).
- **per organization** - bounds a single tenant's aggregate request rate so one
  noisy org cannot starve others (multi-tenant fairness).

Algorithm: a classic token bucket evaluated atomically in Redis via a Lua
script. Each bucket holds up to ``capacity`` tokens and refills at
``refill_rate`` tokens/second. A request consumes one token; if the bucket is
empty the request is rejected and a ``Retry-After`` hint (seconds until the next
token) is returned. State is two hash fields (``tokens``, ``ts``) per bucket with
a TTL so idle buckets evaporate.

Doing the read-modify-write in a single Lua call makes the check atomic across
concurrent workers/instances (the buckets live in shared Redis, design "Data
Stores"), so the limit holds platform-wide rather than per-process.

If Redis is unavailable the limiter *fails open* (allows the request): rate
limiting is a protective measure, not a correctness gate, and the platform must
keep serving traffic when the cache layer hiccups.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# Token-bucket evaluation. KEYS[1] = bucket key. ARGV = capacity, refill_rate,
# now (epoch seconds, float), requested tokens, ttl seconds.
# Returns {allowed (1/0), remaining tokens (int), retry_after seconds (float)}.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

-- Refill based on elapsed time, capped at capacity.
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= requested then
  allowed = 1
  tokens = tokens - requested
else
  local deficit = requested - tokens
  if refill_rate > 0 then
    retry_after = deficit / refill_rate
  else
    retry_after = -1
  end
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)

return {allowed, math.floor(tokens), tostring(retry_after)}
"""


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a single token-bucket check."""

    allowed: bool
    remaining: int
    retry_after: float

    @property
    def retry_after_seconds(self) -> int:
        """Ceil of the retry hint, for the ``Retry-After`` header."""
        if self.retry_after <= 0:
            return 1
        return max(1, int(self.retry_after + 0.999))


@dataclass(frozen=True)
class RateLimitPolicy:
    """Token-bucket parameters for one axis (capacity + refill rate)."""

    capacity: int
    refill_rate: float  # tokens per second

    @property
    def ttl_seconds(self) -> int:
        """How long an idle bucket lives; long enough to fully refill."""
        if self.refill_rate <= 0:
            return 60
        return max(60, int(self.capacity / self.refill_rate) + 60)


# Sensible defaults; the Super_Admin-tunable values (Req 29.4) can override these
# through platform_settings in a later task. IP buckets are tighter than org
# buckets because an org aggregates many legitimate users.
DEFAULT_IP_POLICY = RateLimitPolicy(capacity=120, refill_rate=2.0)
DEFAULT_ORG_POLICY = RateLimitPolicy(capacity=600, refill_rate=10.0)


async def check_rate_limit(
    redis,
    key: str,
    policy: RateLimitPolicy,
    *,
    cost: int = 1,
    now: float | None = None,
) -> RateLimitResult:
    """Consume ``cost`` tokens from the bucket at ``key`` under ``policy``.

    Returns a :class:`RateLimitResult`. Fails open (``allowed=True``) when Redis
    is unavailable or the script errors, so a cache outage never takes the API
    down.
    """
    if redis is None:
        return RateLimitResult(allowed=True, remaining=policy.capacity, retry_after=0.0)

    now = time.time() if now is None else now
    try:
        raw = await redis.eval(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            policy.capacity,
            policy.refill_rate,
            now,
            cost,
            policy.ttl_seconds,
        )
    except Exception:  # pragma: no cover - defensive: never fail closed
        logger.warning("rate_limit_eval_failed", extra={"key": key})
        return RateLimitResult(allowed=True, remaining=policy.capacity, retry_after=0.0)

    allowed = bool(int(raw[0]))
    remaining = int(raw[1])
    retry_after = float(raw[2])
    return RateLimitResult(allowed=allowed, remaining=remaining, retry_after=retry_after)
