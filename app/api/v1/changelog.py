"""Changelog API endpoints (Task 19.5, Req 22).

Surfaces the changelog and the "What's new" popup feed:

    POST /admin/changelog            (Super_Admin) publish an entry      -> {entry}
    GET  /changelog                  list published entries              -> {entries}
    GET  /changelog/unseen           entries newer than last view        -> {show_popup, entries}
    POST /changelog/seen             mark the changelog as seen          -> {last_seen_at}

Publishing makes an entry available to all users (Req 22.1). On sign-in the
frontend calls ``GET /changelog/unseen``; when ``show_popup`` is true it renders
the "What's new" popup with the returned entries (entries published since the
user's ``last_changelog_seen_at``, Req 22.2). Dismissing the popup calls
``POST /changelog/seen`` so it does not reappear for those entries.

The changelog is platform-wide, so these reads only require an authenticated
principal (no tenant scoping); publishing is restricted to the Super_Admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import get_principal, require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.services import changelog_service

router = APIRouter(tags=["changelog"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChangelogEntryOut(BaseModel):
    id: str
    version: str | None = None
    title: str | None = None
    body: str | None = None
    published_at: str | None = None


class PublishChangelogRequest(BaseModel):
    version: str | None = None
    title: str | None = None
    body: str | None = None
    # Publish immediately (default) or store as a draft (published_at NULL).
    publish: bool = True

    model_config = {"extra": "forbid"}


class ChangelogListResponse(BaseModel):
    entries: list[ChangelogEntryOut]


class UnseenChangelogResponse(BaseModel):
    # Drives the "What's new" popup: true when unseen published entries exist.
    show_popup: bool
    entries: list[ChangelogEntryOut]


class MarkSeenResponse(BaseModel):
    last_seen_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/admin/changelog", response_model=ChangelogEntryOut, status_code=201)
async def publish_changelog(
    payload: PublishChangelogRequest,
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ChangelogEntryOut:
    """Publish a changelog entry, making it available to users (Req 22.1)."""
    entry = await changelog_service.publish_entry(
        session,
        version=payload.version,
        title=payload.title,
        body=payload.body,
        publish=payload.publish,
    )
    await session.commit()
    return ChangelogEntryOut(**changelog_service._serialize(entry))


@router.get("/changelog", response_model=ChangelogListResponse)
async def list_changelog(
    _: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> ChangelogListResponse:
    """List all published changelog entries, newest first (Req 22.1)."""
    entries = await changelog_service.list_published(session)
    return ChangelogListResponse(entries=[ChangelogEntryOut(**e) for e in entries])


@router.get("/changelog/unseen", response_model=UnseenChangelogResponse)
async def list_unseen_changelog(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> UnseenChangelogResponse:
    """Return entries published since the caller last viewed (Req 22.2).

    The frontend shows the "What's new" popup when ``show_popup`` is true.
    """
    entries = await changelog_service.list_unseen_for_user(session, principal.user_id)
    return UnseenChangelogResponse(
        show_popup=len(entries) > 0,
        entries=[ChangelogEntryOut(**e) for e in entries],
    )


@router.post("/changelog/seen", response_model=MarkSeenResponse)
async def mark_changelog_seen(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> MarkSeenResponse:
    """Mark the changelog as seen so the popup does not reappear (Req 22.2)."""
    marker = await changelog_service.mark_seen(session, principal.user_id)
    await session.commit()
    return MarkSeenResponse(last_seen_at=marker.isoformat())
