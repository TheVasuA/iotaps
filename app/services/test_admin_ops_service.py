"""Service tests for admin ops: error recording + IP blocking (Task 20.5).

Covers the behaviours the platform's error handler and auth flow depend on:

- Error recording continues on logging failure (Req 28.4).
- Error recording captures user/org/device context (Req 28.2).
- Repeated failed logins from an IP exceeding the threshold block the IP
  (Req 29.3); successful logins never block.

Runs against in-memory SQLite (no live Postgres/Redis required).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

import app.models  # noqa: F401  (register all model tables)
from app.db.base import Base
from app.models.error_log import ErrorLog
from app.models.security import BlockedIp, LoginAttempt
from app.services import admin_ops_service

_TABLES = [
    ErrorLog.__table__,
    LoginAttempt.__table__,
    BlockedIp.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    from sqlalchemy import JSON

    for table in _TABLES:
        id_col = table.c.get("id")
        if id_col is not None:
            id_col.server_default = None
            id_col.default = ColumnDefault(lambda: uuid.uuid4())
    # JSONB columns have no SQLite compiler; use the generic JSON type.
    ErrorLog.__table__.c.detail.type = JSON()


@pytest.fixture()
async def session_factory():
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=_TABLES))


# ---------------------------------------------------------------------------
# Error recording (Req 28.2, 28.4)
# ---------------------------------------------------------------------------
async def test_record_error_captures_context(session_factory):
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    async with session_factory() as s:
        entry = await admin_ops_service.record_error(
            s,
            message="kaboom",
            error_code="internal_error",
            user_id=user_id,
            org_id=org_id,
            device_id=device_id,
        )
        await s.commit()
        assert entry is not None
        assert str(entry.user_id) == user_id
        assert str(entry.org_id) == org_id
        assert str(entry.device_id) == device_id


async def test_record_error_continues_on_failure(session_factory):
    """If recording fails, the platform keeps operating (Req 28.4)."""

    class _BrokenSession:
        def add(self, _obj):
            pass

        async def flush(self):
            raise RuntimeError("db down")

        async def rollback(self):
            return None

    # record_error swallows the failure and returns None rather than raising.
    result = await admin_ops_service.record_error(
        _BrokenSession(),  # type: ignore[arg-type]
        message="will fail",
    )
    assert result is None


async def test_record_error_invalid_context_ignored(session_factory):
    async with session_factory() as s:
        entry = await admin_ops_service.record_error(
            s,
            message="bad ids",
            user_id="not-a-uuid",
            org_id=None,
        )
        await s.commit()
        assert entry is not None
        assert entry.user_id is None
        assert entry.org_id is None


# ---------------------------------------------------------------------------
# IP blocking on threshold (Req 29.3)
# ---------------------------------------------------------------------------
async def test_ip_blocked_after_threshold(session_factory):
    ip = "203.0.113.5"
    async with session_factory() as s:
        threshold, _, _ = await admin_ops_service._failed_login_policy()
        blocked = None
        for _ in range(threshold):
            blocked = await admin_ops_service.record_login_attempt(
                s, ip=ip, email="a@b.com", success=False
            )
        await s.commit()
        # The attempt that reaches the threshold creates the block (Req 29.3).
        assert blocked is not None
        assert blocked.ip == ip
        assert await admin_ops_service.is_ip_blocked(s, ip) is True

        rows = (
            (await s.execute(select(BlockedIp).where(BlockedIp.ip == ip)))
            .scalars()
            .all()
        )
        assert len(rows) == 1


async def test_below_threshold_not_blocked(session_factory):
    ip = "203.0.113.9"
    async with session_factory() as s:
        threshold, _, _ = await admin_ops_service._failed_login_policy()
        result = None
        for _ in range(threshold - 1):
            result = await admin_ops_service.record_login_attempt(
                s, ip=ip, email="a@b.com", success=False
            )
        await s.commit()
        assert result is None
        assert await admin_ops_service.is_ip_blocked(s, ip) is False


async def test_successful_login_never_blocks(session_factory):
    ip = "203.0.113.20"
    async with session_factory() as s:
        threshold, _, _ = await admin_ops_service._failed_login_policy()
        for _ in range(threshold + 2):
            result = await admin_ops_service.record_login_attempt(
                s, ip=ip, email="a@b.com", success=True
            )
            assert result is None
        await s.commit()
        assert await admin_ops_service.is_ip_blocked(s, ip) is False
