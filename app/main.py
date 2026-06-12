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
from sqlalchemy import select

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


async def _seed_superadmin(logger):
    """Create the super_admin user from env vars if not already present.

    This runs on every startup but is idempotent: if the email already exists,
    it ensures the role is super_admin (in case it was manually changed).
    """
    settings = get_settings()
    if not settings.superadmin_email or not settings.superadmin_password:
        return

    from app.db.session import async_session_factory
    from app.models.user import User
    from app.models.organization import Organization
    from app.core.security.password import hash_password

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.email == settings.superadmin_email)
            )
            user = result.scalar_one_or_none()

            if user is None:
                # Need an org for the user
                org_result = await session.execute(select(Organization).limit(1))
                org = org_result.scalar_one_or_none()
                if org is None:
                    org = Organization(name="Platform Admin")
                    session.add(org)
                    await session.flush()

                user = User(
                    org_id=org.id,
                    email=settings.superadmin_email,
                    gmail_identity=settings.superadmin_email,
                    password_hash=hash_password(settings.superadmin_password),
                    password_format="argon2",
                    role="super_admin",
                    twofa_enabled=False,
                )
                session.add(user)
                await session.commit()
                logger.info("superadmin_seeded", extra={"email": settings.superadmin_email})
            elif user.role != "super_admin":
                user.role = "super_admin"
                await session.commit()
                logger.info("superadmin_role_fixed", extra={"email": settings.superadmin_email})
            else:
                logger.info("superadmin_exists", extra={"email": settings.superadmin_email})
    except Exception as exc:
        logger.warning("superadmin_seed_failed", extra={"error": str(exc)})


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

    # Auto-seed super admin from env vars (SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
    # so fresh deployments don't require manual DB manipulation.
    await _seed_superadmin(logger)

    logger.info("application_startup", extra={"env": get_settings().app_env})
    yield
    # Clean up persistent connections on shutdown.
    from app.api.v1.commands import _mqtt_pool
    await _mqtt_pool.close()
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
