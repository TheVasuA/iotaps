"""Profile display name and 2FA backup code hashes.

Revision ID: 0004_profile_2fa
Revises: 0003_account_types
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_profile_2fa"
down_revision: Union[str, None] = "0003_account_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("twofa_backup_hashes", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "twofa_backup_hashes")
    op.drop_column("users", "display_name")
