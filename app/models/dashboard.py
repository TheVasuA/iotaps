"""Dashboard-domain models: dashboards, widgets. See design.md Table Catalog."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, uuid_pk


class Dashboard(Base, TenantMixin, TimestampMixin):
    """A user-configurable arrangement of widgets (Req 7, 8)."""

    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # public share token (Req 8)
    public_token: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    layout: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class Widget(Base, TenantMixin):
    """A single visual component on a dashboard (Req 7)."""

    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = uuid_pk()
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # line/gauge/bar/value/map/toggle/slider/alert_badge
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # data binding, thresholds
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # x,y,w,h (React Grid Layout)
    layout: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # (Req 7.5)
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # chart annotations (Req 7.6)
    annotations: Mapped[list | None] = mapped_column(
        JSONB, nullable=False, server_default="'[]'"
    )
