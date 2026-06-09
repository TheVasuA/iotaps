"""Rate-limit middleware - stage 1 of the middleware stack (design.md).

This is the outermost stage of the documented order:

    1. Rate limiting (Redis token bucket; per IP + per org)   <-- this module
    2. JWT verification  -> principal {user_id, org_id, role}
    3. RBAC authorization
    4. Tenant filter

Rate limiting runs *before* authentication so floods are shed cheaply. It is
implemented as ASGI middleware (it must see every request, including
unauthenticated auth routes), whereas JWT verify / RBAC / tenant filter are
implemented as FastAPI dependencies (design notes they "can be FastAPI
dependencies") so individual routes opt into authentication and declare their
role/tenant requirements.

Per-IP limiting always applies. Per-org limiting additionally applies when the
request carries a decodable bearer token, so a single tenant's aggregate rate is
bounded even across many users/IPs. Token decoding here is best-effort and never
rejects the request - authentication proper happens in the dependency layer.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.core.rate_limit import (
    DEFAULT_IP_POLICY,
    DEFAULT_ORG_POLICY,
    RateLimitPolicy,
    check_rate_limit,
)
from app.core.redis_client import get_redis
from app.core.redis_keys import rate_limit_ip_key, rate_limit_org_key
from app.core.security import jwt as jwt_service

logger = get_logger(__name__)


def _client_ip(request: Request) -> str:
    """Resolve the client IP, honouring a reverse-proxy ``X-Forwarded-For``.

    Nginx/Cloudflare front the API (design "Edge"), so the first hop in
    ``X-Forwarded-For`` is the real client. Falls back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _bearer_org_id(request: Request) -> str | None:
    """Best-effort org_id extraction from the bearer token (no rejection)."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt_service.decode_access_token(token)
    except jwt_service.TokenError:
        return None
    return claims.org_id or None


def _rejection(retry_after: int, scope: str) -> Response:
    """429 response with a ``Retry-After`` header and structured body."""
    response = JSONResponse(
        status_code=429,
        content={
            "error_code": "rate_limited",
            "message": "Too many requests. Please slow down and retry shortly.",
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Scope"] = scope
    return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiting per client IP and per organization."""

    def __init__(
        self,
        app,
        *,
        ip_policy: RateLimitPolicy = DEFAULT_IP_POLICY,
        org_policy: RateLimitPolicy = DEFAULT_ORG_POLICY,
        exempt_paths: tuple[str, ...] = ("/api/v1/health", "/api/v1/docs", "/api/v1/openapi.json"),
    ) -> None:
        super().__init__(app)
        self.ip_policy = ip_policy
        self.org_policy = org_policy
        self.exempt_paths = exempt_paths

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in self.exempt_paths):
            return await call_next(request)

        redis = get_redis()

        # Per-IP bucket (always applies).
        ip = _client_ip(request)
        ip_result = await check_rate_limit(redis, rate_limit_ip_key(ip), self.ip_policy)
        if not ip_result.allowed:
            logger.warning("rate_limited_ip", extra={"ip": ip, "path": path})
            return _rejection(ip_result.retry_after_seconds, "ip")

        # Per-org bucket (applies when an org can be derived from the token).
        org_id = _bearer_org_id(request)
        if org_id:
            org_result = await check_rate_limit(
                redis, rate_limit_org_key(org_id), self.org_policy
            )
            if not org_result.allowed:
                logger.warning("rate_limited_org", extra={"org_id": org_id, "path": path})
                return _rejection(org_result.retry_after_seconds, "org")

        return await call_next(request)
