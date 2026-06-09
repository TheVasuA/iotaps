"""Health endpoint (Req 28.1).

Reports overall API liveness plus the reachability of core dependencies
(Redis now; PostgreSQL/TimescaleDB/MQTT are added as those integrations land in
later tasks). This is the foundation for the Super_Admin service-status view.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.redis_client import get_redis

router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    name: str
    status: str  # "ok" | "degraded" | "unconfigured"


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    service: str
    dependencies: list[DependencyStatus]


async def _check_redis() -> DependencyStatus:
    redis = get_redis()
    if redis is None:
        return DependencyStatus(name="redis", status="unconfigured")
    try:
        await redis.ping()
        return DependencyStatus(name="redis", status="ok")
    except Exception:
        return DependencyStatus(name="redis", status="degraded")


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health() -> HealthResponse:
    """Return API liveness and dependency status."""
    deps = [await _check_redis()]
    overall = "ok" if all(d.status in {"ok", "unconfigured"} for d in deps) else "degraded"
    return HealthResponse(status=overall, service="iotaps-api", dependencies=deps)
