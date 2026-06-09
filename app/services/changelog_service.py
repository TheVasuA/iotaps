"""Changelog publishing and "What's new" popup logic (Task 19.5, Req 22).

Implements the changelog surface behind the API:

- **Publish entries (Req 22.1).** :func:`publish_entry` creates a ``changelog``
  row and stamps ``published_at`` so the entry becomes available to users. An
  entry without a ``published_at`` is a draft and is never surfaced.
- **"What's new" popup (Req 22.2).** :func:`list_unseen_for_user` returns the
  published entries newer than the user's ``last_changelog_seen_at`` - exactly
  the entries that should drive the popup on sign-in. When the user has never
  viewed the changelog (``last_changelog_seen_at`` is NULL) every published
  entry is unseen.
- **Mark seen.** :func:`mark_seen` advances the user's
  ``last_changelog_seen_at`` to the latest published entry's timestamp (or
  "now" when no entry is newer), so the popup does not reappear for entries the
  user has already been shown.

The changelog is platform-wide (not tenant-scoped): an entry published by the
Super_Admin is visible to every organization's users.

Callers are responsible for committing the surrounding transaction.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.ops import Changelog
from app.models.user import User

logger = get_logger(__name__)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_aware(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Normalise a stored timestamp to a timezone-aware UTC value.

    SQLite round-trips ``DateTime`` columns as naive datetimes; treat a naive
    value as UTC so comparisons against ``last_changelog_seen_at`` are correct
    regardless of the backing database.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _serialize(entry: Changelog) -> dict[str, Any]:
    published = _as_aware(entry.published_at)
    return {
        "id": str(entry.id),
        "version": entry.version,
        "title": entry.title,
        "body": entry.body,
        "published_at": published.isoformat() if published else None,
    }


async def publish_entry(
    session: AsyncSession,
    *,
    version: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    publish: bool = True,
    published_at: Optional[datetime.datetime] = None,
) -> Changelog:
    """Create a changelog entry, publishing it so users can see it (Req 22.1).

    ``publish=True`` (the default) stamps ``published_at`` (using ``now`` when
    not supplied), which is what makes the entry available to users and able to
    trigger the "What's new" popup. ``publish=False`` stores a draft with a NULL
    ``published_at`` that is never surfaced until published.
    """
    if not (title or body or version):
        raise ValidationError(
            "A changelog entry requires at least a version, title, or body",
            error_code="changelog_empty",
        )

    stamp: Optional[datetime.datetime] = None
    if publish:
        stamp = published_at or _now()

    entry = Changelog(version=version, title=title, body=body, published_at=stamp)
    session.add(entry)
    await session.flush()
    logger.info(
        "changelog_published" if publish else "changelog_drafted",
        extra={"changelog_id": str(entry.id), "version": version},
    )
    return entry


async def list_published(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all published changelog entries, newest first (Req 22.1)."""
    rows = (
        await session.execute(
            select(Changelog)
            .where(Changelog.published_at.is_not(None))
            .order_by(Changelog.published_at.desc())
        )
    ).scalars().all()
    return [_serialize(e) for e in rows]


def _coerce_user_id(user_id: Any) -> uuid.UUID:
    try:
        return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (ValueError, TypeError) as exc:
        raise ValidationError("Invalid user id") from exc


async def list_unseen_for_user(
    session: AsyncSession, user_id: Any
) -> list[dict[str, Any]]:
    """Return published entries newer than the user's last view (Req 22.2).

    These are the entries the "What's new" popup should present on sign-in. When
    the user has never viewed the changelog (``last_changelog_seen_at`` is
    NULL), every published entry is unseen. Entries are returned newest first.
    """
    user_uuid = _coerce_user_id(user_id)
    user = await session.get(User, user_uuid)
    if user is None:
        raise NotFoundError("User not found")

    stmt = select(Changelog).where(Changelog.published_at.is_not(None))
    seen_at = _as_aware(user.last_changelog_seen_at)
    if seen_at is not None:
        stmt = stmt.where(Changelog.published_at > seen_at)
    stmt = stmt.order_by(Changelog.published_at.desc())

    rows = (await session.execute(stmt)).scalars().all()
    return [_serialize(e) for e in rows]


async def mark_seen(
    session: AsyncSession,
    user_id: Any,
    *,
    seen_at: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """Advance the user's ``last_changelog_seen_at`` so seen entries don't recur.

    Sets the marker to ``seen_at`` (default "now"), but never earlier than the
    latest published entry, so once a user dismisses the popup every currently
    published entry counts as seen. Returns the timestamp stored.
    """
    user_uuid = _coerce_user_id(user_id)
    user = await session.get(User, user_uuid)
    if user is None:
        raise NotFoundError("User not found")

    marker = seen_at or _now()

    latest = (
        await session.execute(
            select(Changelog.published_at)
            .where(Changelog.published_at.is_not(None))
            .order_by(Changelog.published_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest = _as_aware(latest)
    if latest is not None and latest > marker:
        marker = latest

    user.last_changelog_seen_at = marker
    await session.flush()
    return marker
