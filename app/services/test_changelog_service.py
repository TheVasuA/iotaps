"""Unit tests for the changelog "What's new" popup trigger (Task 19.6, Req 22.2).

These exercise the service logic directly (``list_unseen_for_user`` /
``mark_seen``) to assert the precise condition that drives the popup: it shows
*only* when published entries exist that are newer than the user's
``last_changelog_seen_at``. The endpoint tests in
``app/api/v1/test_changelog_endpoints.py`` cover the HTTP wiring; here we focus
on the boundary and edge cases of the trigger decision itself.

Uses an in-memory SQLite async session (no live Postgres). Only the tables the
changelog path touches are created, and their Postgres ``gen_random_uuid()`` PK
defaults are swapped for Python uuid4 so SQLite can evaluate them.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import NotFoundError
from app.db.base import Base
from app.models.ops import Changelog
from app.models.organization import Organization
from app.models.user import User
from app.services import changelog_service as cs

_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Changelog.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Swap each table's ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture
async def session() -> AsyncSession:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _at(offset_seconds: int) -> datetime.datetime:
    """A deterministic timezone-aware timestamp relative to a fixed base."""
    base = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


async def _add_user(
    session: AsyncSession, *, last_seen: datetime.datetime | None = None
) -> User:
    org = Organization(name="Acme", plan="free")
    session.add(org)
    await session.flush()
    user = User(
        org_id=org.id,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role="device_user",
        last_changelog_seen_at=last_seen,
    )
    session.add(user)
    await session.flush()
    return user


def _popup_shows(entries: list) -> bool:
    """Mirror the endpoint's trigger rule: popup shows iff unseen entries exist."""
    return len(entries) > 0


# ---------------------------------------------------------------------------
# Popup shows only when unseen entries exist since last view (Req 22.2)
# ---------------------------------------------------------------------------
async def test_no_published_entries_no_popup(session):
    """An empty changelog never triggers the popup."""
    user = await _add_user(session)
    entries = await cs.list_unseen_for_user(session, user.id)
    assert entries == []
    assert _popup_shows(entries) is False


async def test_never_seen_user_sees_all_published(session):
    """A user who has never viewed the changelog sees every published entry."""
    await cs.publish_entry(session, title="One", published_at=_at(0))
    await cs.publish_entry(session, title="Two", published_at=_at(10))
    user = await _add_user(session, last_seen=None)

    entries = await cs.list_unseen_for_user(session, user.id)
    assert _popup_shows(entries) is True
    assert [e["title"] for e in entries] == ["Two", "One"]  # newest first


async def test_all_entries_seen_no_popup(session):
    """When last view is at/after the newest entry, the popup does not show."""
    await cs.publish_entry(session, title="One", published_at=_at(0))
    await cs.publish_entry(session, title="Two", published_at=_at(10))
    user = await _add_user(session, last_seen=_at(20))

    entries = await cs.list_unseen_for_user(session, user.id)
    assert entries == []
    assert _popup_shows(entries) is False


async def test_only_entries_after_last_view_are_unseen(session):
    """Only entries strictly newer than last view drive the popup."""
    await cs.publish_entry(session, title="Old", published_at=_at(0))
    await cs.publish_entry(session, title="New", published_at=_at(100))
    user = await _add_user(session, last_seen=_at(50))

    entries = await cs.list_unseen_for_user(session, user.id)
    assert _popup_shows(entries) is True
    assert [e["title"] for e in entries] == ["New"]


async def test_entry_at_exact_last_view_is_seen(session):
    """Boundary: an entry published exactly at last view counts as seen (strict >)."""
    await cs.publish_entry(session, title="Exact", published_at=_at(50))
    user = await _add_user(session, last_seen=_at(50))

    entries = await cs.list_unseen_for_user(session, user.id)
    assert entries == []
    assert _popup_shows(entries) is False


async def test_draft_entries_never_trigger_popup(session):
    """Unpublished drafts (published_at NULL) are never unseen, even for new users."""
    await cs.publish_entry(session, title="Draft", publish=False)
    user = await _add_user(session, last_seen=None)

    entries = await cs.list_unseen_for_user(session, user.id)
    assert entries == []
    assert _popup_shows(entries) is False


async def test_mark_seen_then_no_popup(session):
    """After mark_seen, previously unseen entries stop triggering the popup."""
    await cs.publish_entry(session, title="One", published_at=_at(0))
    user = await _add_user(session, last_seen=None)
    assert _popup_shows(await cs.list_unseen_for_user(session, user.id)) is True

    await cs.mark_seen(session, user.id)
    entries = await cs.list_unseen_for_user(session, user.id)
    assert entries == []
    assert _popup_shows(entries) is False


async def test_entry_published_after_mark_seen_retriggers_popup(session):
    """A newer entry published after the user viewed re-triggers the popup."""
    await cs.publish_entry(session, title="One", published_at=_at(0))
    user = await _add_user(session, last_seen=None)
    # Pin the seen marker to a deterministic instant after the first entry.
    await cs.mark_seen(session, user.id, seen_at=_at(50))
    assert _popup_shows(await cs.list_unseen_for_user(session, user.id)) is False

    # A newer entry appears after the user marked the changelog seen.
    await cs.publish_entry(session, title="Two", published_at=_at(100))
    entries = await cs.list_unseen_for_user(session, user.id)
    assert _popup_shows(entries) is True
    assert [e["title"] for e in entries] == ["Two"]


async def test_list_unseen_unknown_user_raises(session):
    """An unknown user id is rejected rather than silently showing no popup."""
    with pytest.raises(NotFoundError):
        await cs.list_unseen_for_user(session, uuid.uuid4())
