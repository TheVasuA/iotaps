"""Organization (tenant) model. See design.md Table Catalog: organizations."""

from __future__ import annotations

import uuid

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class Organization(Base, TimestampMixin):
    """A tenant boundary (a Project_Center maps to one Organization)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # project_center / platform
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # free / pro
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    # active / suspended
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    # per-partner commission override (Req 18.2, 26.2)
    commission_rate_override: Mapped[float | None] = mapped_column(
        Numeric, nullable=True
    )
    referral_code: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
