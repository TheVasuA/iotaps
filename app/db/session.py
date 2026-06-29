"""Async SQLAlchemy engine/session factory.

The application uses the async driver (``asyncpg``) configured via ``DATABASE_URL``.
Alembic migrations run with a synchronous driver derived from the same URL (see
``alembic/env.py``).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def _make_engine():
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        future=True,
        # Connection pool tuning for stability under sustained load:
        #   pool_size      — base connections kept open per process
        #   max_overflow   — extra connections allowed during bursts
        #   pool_recycle   — recycle connections after 30min to shed stale ones
        #                    (prevents "server closed the connection" after days)
        #   pool_timeout   — fail fast rather than hang if the pool is exhausted
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=30,
    )


engine = _make_engine()

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """FastAPI dependency yielding a request-scoped async session."""
    async with async_session_factory() as session:
        yield session
