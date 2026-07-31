"""Add datastream registry columns to device_sensors.

Revision ID: 0002
Revises: 0001_initial_schema
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0002"
# Must match the `revision` identifier declared in 0001, which is
# "0001_initial" — not the module filename ("0001_initial_schema").
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns for the datastream registry feature
    op.add_column(
        "device_sensors",
        sa.Column("pin_type", sa.Text(), nullable=False, server_default="sensor"),
    )
    op.add_column(
        "device_sensors",
        sa.Column("min_value", sa.Float(), nullable=True),
    )
    op.add_column(
        "device_sensors",
        sa.Column("max_value", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_sensors", "max_value")
    op.drop_column("device_sensors", "min_value")
    op.drop_column("device_sensors", "pin_type")
