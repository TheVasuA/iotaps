"""SQLAlchemy declarative base and shared column mixins.

Conventions (design.md "Table Catalog"):
- Every table uses a UUID primary key generated server-side via ``gen_random_uuid()``.
- Every *tenant* table carries ``org_id UUID NOT NULL`` (FK -> organizations) and is
  indexed on ``org_id`` (Req 3.1 multi-tenant isolation).
- Most tables carry ``created_at TIMESTAMPTZ DEFAULT now()``.

A deterministic naming convention is configured so Alembic autogenerates stable
constraint/index names across environments.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

# Stable naming convention -> reproducible migration names.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """A server-generated UUID primary key column."""
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Adds a ``created_at TIMESTAMPTZ DEFAULT now()`` column."""

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenantMixin:
    """Adds the mandatory, indexed ``org_id`` tenant key (Req 3.1).

    Declared as a mixin so every tenant-owned table enforces
    ``org_id UUID NOT NULL`` with an index, without repeating the column.
    """

    @declared_attr
    def org_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
