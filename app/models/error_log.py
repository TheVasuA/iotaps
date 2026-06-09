"""Platform error log model (Req 28.2, 28.3).

Records platform errors together with the associated user, Organization, and
Device context so the Super_Admin can review recent errors and error trends.
This is a platform-wide operational table (not tenant-scoped): ``org_id`` is a
nullable context column rather than a mandatory tenant key, because an error may
occur with no organization context at all (e.g. anonymous/auth failures).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class ErrorLog(Base, TimestampMixin):
    """A recorded platform error with user/org/device context (Req 28.2)."""

    __tablename__ = "error_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Machine-readable error code (mirrors app.core.errors codes when known).
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Context (Req 28.2): all nullable - an error may lack any of these.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    # Any extra structured context for diagnosis.
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
