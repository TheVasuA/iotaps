"""Alembic migration environment for IoTAPS.

Resolves the database URL from the ``DATABASE_URL`` environment variable and
coerces it to a synchronous driver (psycopg2) for migration execution, since
Alembic runs migrations synchronously. All ORM models are imported so that
``target_metadata`` reflects the full schema for autogeneration.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure the project root (parent of the `app/` package) is importable,
# regardless of the directory Alembic is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Import the metadata with every model registered.
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url() -> str:
    """Return a synchronous SQLAlchemy URL for migrations."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://iotaps:change_me_postgres@localhost:5432/iotaps",
    )
    # Migrations run synchronously: swap async drivers for psycopg2.
    return url.replace("+asyncpg", "+psycopg2").replace(
        "postgresql://", "postgresql+psycopg2://"
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
