"""IoTAPS FastAPI application entrypoint.

Builds the application via `create_app()` and exposes `app` as the ASGI target
for the gunicorn/uvicorn command in the Dockerfile / docker-compose.yml
(`gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker`).

Wires the full request pipeline for the skeleton:
  - JSON structured logging
  - Request ID propagation + JSON access logging
  - CORS
  - Structured error bodies ({error_code, message})
  - Versioned /api/v1 router with a health endpoint
  - Redis-backed platform settings loader lifecycle
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ws import router as ws_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware
from app.core.redis_client import close_redis
from app.core.security.rate_limit_middleware import RateLimitMiddleware
from app.core.settings_loader import get_all_settings

API_V1_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger = get_logger(__name__)

    # Warm the platform settings read-through cache so the first request does
    # not pay the cold-cache penalty. Best-effort: never block startup.
    try:
        await get_all_settings()
    except Exception:
        logger.warning("platform_settings_warm_failed")

    logger.info("application_startup", extra={"env": get_settings().app_env})
    yield
    await close_redis()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Application factory: build and configure the FastAPI app."""
    settings = get_settings()
    configure_logging("DEBUG" if settings.app_debug else "INFO")

    app = FastAPI(
        title="IoTAPS Platform API",
        version="1.0.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )

    # --- Middleware (added bottom-up; request id is outermost) ---
    # Execution order per request: RequestID -> RateLimit -> CORS -> app, so
    # rate-limited (429) responses still carry a request id / access log, and
    # rate limiting (stage 1 of the design's middleware stack) runs before any
    # route handling. JWT verify / RBAC / tenant filter (stages 2-4) are applied
    # as FastAPI dependencies on individual routes (see app.core.security.deps).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # --- Structured error handlers ({error_code, message}) ---
    register_exception_handlers(app)

    # --- Routers ---
    app.include_router(api_v1_router, prefix=API_V1_PREFIX)
    # WebSocket gateway mounted at the root (/ws) per design; Nginx routes WS
    # traffic here separately from the REST API (Req 6.4, 7.4).
    app.include_router(ws_router)

    return app


app = create_app()
