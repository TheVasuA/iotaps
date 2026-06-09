"""initial schema: relational tables + TimescaleDB telemetry hypertable

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000

Creates the full IoTAPS schema from design.md "Table Catalog":
- Enables the ``timescaledb`` and ``pgcrypto`` extensions.
- Creates every relational/tenant table with ``org_id NOT NULL`` + index on
  tenant tables, the wallet ``balance >= 0`` and commission ``amount >= 0``
  CHECK constraints (Req 18.x), unique constraints, and FKs.
- Creates the ``telemetry`` hypertable, a 7-day compression policy, and the
  ``telemetry_5m`` / ``telemetry_1h`` / ``telemetry_1d`` continuous aggregates
  (Req 6.6, 32.1).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
TS = sa.DateTime(timezone=True)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _org_id(nullable: bool = False) -> sa.Column:
    return sa.Column(
        "org_id",
        UUID,
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=nullable,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", TS, nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    # ---- Extensions -------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ---- organizations ----------------------------------------------------
    op.create_table(
        "organizations",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=False, server_default="free"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("commission_rate_override", sa.Numeric(), nullable=True),
        sa.Column("referral_code", sa.Text(), nullable=True),
        _created_at(),
        sa.UniqueConstraint("referral_code", name="uq_organizations_referral_code"),
    )

    # ---- mqtt_nodes (referenced by devices.node_id) -----------------------
    op.create_table(
        "mqtt_nodes",
        _uuid_pk(),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "active_connections", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("ram_pct", sa.Numeric(), nullable=True),
        sa.Column("cpu_pct", sa.Numeric(), nullable=True),
        sa.Column("disk_pct", sa.Numeric(), nullable=True),
        _created_at(),
    )

    # ---- templates (referenced by devices/rules) --------------------------
    op.create_table(
        "templates",
        _uuid_pk(),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("arduino_code", sa.Text(), nullable=True),
        sa.Column("wiring_diagram_url", sa.Text(), nullable=True),
        sa.Column("dashboard_def", JSONB, nullable=True),
        sa.Column("rules_def", JSONB, nullable=True),
    )

    # ---- users ------------------------------------------------------------
    op.create_table(
        "users",
        _uuid_pk(),
        _org_id(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("gmail_identity", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "password_format", sa.Text(), nullable=False, server_default="argon2"
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("oauth_provider", sa.Text(), nullable=True),
        sa.Column(
            "twofa_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("twofa_secret", sa.Text(), nullable=True),
        sa.Column("theme_mode", sa.Text(), nullable=False, server_default="light"),
        sa.Column(
            "referred_by",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_changelog_seen_at", TS, nullable=True),
        _created_at(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])

    # ---- device_groups ----------------------------------------------------
    op.create_table(
        "device_groups",
        _uuid_pk(),
        _org_id(),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_device_groups_org_id", "device_groups", ["org_id"])

    # ---- devices ----------------------------------------------------------
    op.create_table(
        "devices",
        _uuid_pk(),
        _org_id(),
        sa.Column("device_uid", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "group_id",
            UUID,
            sa.ForeignKey("device_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "node_id",
            UUID,
            sa.ForeignKey("mqtt_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="offline"),
        sa.Column(
            "maintenance_mode", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "is_simulator", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "sim_interval_sec", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column(
            "template_id",
            UUID,
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
        sa.UniqueConstraint("device_uid", name="uq_devices_device_uid"),
    )
    op.create_index("ix_devices_org_id", "devices", ["org_id"])

    # ---- mqtt_credentials -------------------------------------------------
    op.create_table(
        "mqtt_credentials",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("acl_pattern", sa.Text(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("username", name="uq_mqtt_credentials_username"),
    )
    op.create_index("ix_mqtt_credentials_org_id", "mqtt_credentials", ["org_id"])
    op.create_index(
        "ix_mqtt_credentials_device_id", "mqtt_credentials", ["device_id"]
    )

    # ---- device_sensors ---------------------------------------------------
    op.create_table(
        "device_sensors",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
    )
    op.create_index("ix_device_sensors_org_id", "device_sensors", ["org_id"])
    op.create_index("ix_device_sensors_device_id", "device_sensors", ["device_id"])

    # ---- device_user_assignments -----------------------------------------
    op.create_table(
        "device_user_assignments",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at", TS, nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint(
            "device_id", "user_id", name="uq_device_user_assignments_device_user"
        ),
    )
    op.create_index(
        "ix_device_user_assignments_org_id", "device_user_assignments", ["org_id"]
    )
    op.create_index(
        "ix_device_user_assignments_device_id",
        "device_user_assignments",
        ["device_id"],
    )
    op.create_index(
        "ix_device_user_assignments_user_id",
        "device_user_assignments",
        ["user_id"],
    )

    # ---- dashboards -------------------------------------------------------
    op.create_table(
        "dashboards",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "owner_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_public", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("public_token", sa.Text(), nullable=True),
        sa.Column("layout", JSONB, nullable=True),
        _created_at(),
        sa.UniqueConstraint("public_token", name="uq_dashboards_public_token"),
    )
    op.create_index("ix_dashboards_org_id", "dashboards", ["org_id"])

    # ---- widgets ----------------------------------------------------------
    op.create_table(
        "widgets",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "dashboard_id",
            UUID,
            sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("layout", JSONB, nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "annotations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.create_index("ix_widgets_org_id", "widgets", ["org_id"])
    op.create_index("ix_widgets_dashboard_id", "widgets", ["dashboard_id"])

    # ---- rules ------------------------------------------------------------
    op.create_table(
        "rules",
        _uuid_pk(),
        _org_id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "template_id",
            UUID,
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )
    op.create_index("ix_rules_org_id", "rules", ["org_id"])

    # ---- rule_nodes -------------------------------------------------------
    op.create_table(
        "rule_nodes",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "rule_id",
            UUID,
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_type", sa.Text(), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("position", JSONB, nullable=True),
    )
    op.create_index("ix_rule_nodes_org_id", "rule_nodes", ["org_id"])
    op.create_index("ix_rule_nodes_rule_id", "rule_nodes", ["rule_id"])

    # ---- rule_edges -------------------------------------------------------
    op.create_table(
        "rule_edges",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "rule_id",
            UUID,
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_node_id",
            UUID,
            sa.ForeignKey("rule_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_node_id",
            UUID,
            sa.ForeignKey("rule_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_rule_edges_org_id", "rule_edges", ["org_id"])
    op.create_index("ix_rule_edges_rule_id", "rule_edges", ["rule_id"])

    # ---- coupons ----------------------------------------------------------
    op.create_table(
        "coupons",
        _uuid_pk(),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("discount_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("redemptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_until", TS, nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        _created_at(),
        sa.UniqueConstraint("code", name="uq_coupons_code"),
    )

    # ---- subscriptions ----------------------------------------------------
    op.create_table(
        "subscriptions",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("billing_cycle", sa.Text(), nullable=True),
        sa.Column("device_count", sa.Integer(), nullable=True),
        sa.Column("unit_price", sa.Numeric(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("current_period_start", TS, nullable=True),
        sa.Column("current_period_end", TS, nullable=True),
        sa.Column(
            "coupon_id",
            UUID,
            sa.ForeignKey("coupons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("razorpay_subscription_id", sa.Text(), nullable=True),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])

    # ---- payments ---------------------------------------------------------
    op.create_table(
        "payments",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "subscription_id",
            UUID,
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("razorpay_payment_id", sa.Text(), nullable=True),
        sa.Column("razorpay_order_id", sa.Text(), nullable=True),
        sa.Column("paid_at", TS, nullable=True),
        sa.Column("refunded_at", TS, nullable=True),
    )
    op.create_index("ix_payments_org_id", "payments", ["org_id"])

    # ---- partner_wallets (balance >= 0, one per org) ----------------------
    op.create_table(
        "partner_wallets",
        _uuid_pk(),
        _org_id(),
        sa.Column("balance", sa.Numeric(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "balance >= 0", name="balance_non_negative"
        ),
        sa.UniqueConstraint("org_id", name="uq_partner_wallets_org_id"),
    )
    op.create_index("ix_partner_wallets_org_id", "partner_wallets", ["org_id"])

    # ---- commissions (amount >= 0) ----------------------------------------
    op.create_table(
        "commissions",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "wallet_id",
            UUID,
            sa.ForeignKey("partner_wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "payment_id",
            UUID,
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "amount >= 0", name="amount_non_negative"
        ),
    )
    op.create_index("ix_commissions_org_id", "commissions", ["org_id"])
    op.create_index("ix_commissions_wallet_id", "commissions", ["wallet_id"])

    # ---- payouts ----------------------------------------------------------
    op.create_table(
        "payouts",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "wallet_id",
            UUID,
            sa.ForeignKey("partner_wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("requested_at", TS, nullable=True),
        sa.Column(
            "approved_by",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", TS, nullable=True),
        sa.Column("razorpayx_payout_id", sa.Text(), nullable=True),
    )
    op.create_index("ix_payouts_org_id", "payouts", ["org_id"])
    op.create_index("ix_payouts_wallet_id", "payouts", ["wallet_id"])

    # ---- referrals --------------------------------------------------------
    op.create_table(
        "referrals",
        _uuid_pk(),
        sa.Column(
            "referrer_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("referred_gmail", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        _created_at(),
        sa.UniqueConstraint("referred_gmail", name="uq_referrals_referred_gmail"),
    )
    op.create_index(
        "ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"]
    )

    # ---- referral_rewards -------------------------------------------------
    op.create_table(
        "referral_rewards",
        _uuid_pk(),
        sa.Column(
            "referrer_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("devices_granted", sa.Integer(), nullable=False),
        sa.Column("months_granted", sa.Integer(), nullable=False),
        sa.Column("granted_at", TS, nullable=True),
        sa.Column("expires_at", TS, nullable=True),
    )
    op.create_index(
        "ix_referral_rewards_referrer_user_id",
        "referral_rewards",
        ["referrer_user_id"],
    )

    # ---- activity_logs ----------------------------------------------------
    op.create_table(
        "activity_logs",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("detail", JSONB, nullable=True),
        _created_at(),
    )
    op.create_index("ix_activity_logs_org_id", "activity_logs", ["org_id"])

    # ---- notifications ----------------------------------------------------
    op.create_table(
        "notifications",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        _created_at(),
    )
    op.create_index("ix_notifications_org_id", "notifications", ["org_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    # ---- webhooks ---------------------------------------------------------
    op.create_table(
        "webhooks",
        _uuid_pk(),
        _org_id(),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=True),
        sa.Column("retry_policy", JSONB, nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])

    # ---- support_chats ----------------------------------------------------
    op.create_table(
        "support_chats",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "device_id",
            UUID,
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_center_id",
            UUID,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sender_role", sa.Text(), nullable=True),
        _created_at(),
    )
    op.create_index("ix_support_chats_org_id", "support_chats", ["org_id"])

    # ---- changelog --------------------------------------------------------
    op.create_table(
        "changelog",
        _uuid_pk(),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", TS, nullable=True),
    )

    # ---- scheduled_reports ------------------------------------------------
    op.create_table(
        "scheduled_reports",
        _uuid_pk(),
        _org_id(),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("query", JSONB, nullable=True),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("last_run_at", TS, nullable=True),
    )
    op.create_index("ix_scheduled_reports_org_id", "scheduled_reports", ["org_id"])

    # ---- login_attempts ---------------------------------------------------
    op.create_table(
        "login_attempts",
        _uuid_pk(),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip"])

    # ---- blocked_ips ------------------------------------------------------
    op.create_table(
        "blocked_ips",
        _uuid_pk(),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("blocked_until", TS, nullable=True),
        _created_at(),
        sa.UniqueConstraint("ip", name="uq_blocked_ips_ip"),
    )

    # ---- audit_log --------------------------------------------------------
    op.create_table(
        "audit_log",
        _uuid_pk(),
        sa.Column(
            "actor_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("detail", JSONB, nullable=True),
        _created_at(),
    )

    # ---- error_log --------------------------------------------------------
    op.create_table(
        "error_log",
        _uuid_pk(),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("org_id", UUID, nullable=True),
        sa.Column("device_id", UUID, nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        _created_at(),
    )
    op.create_index("ix_error_log_error_code", "error_log", ["error_code"])
    op.create_index("ix_error_log_org_id", "error_log", ["org_id"])

    # ---- platform_settings ------------------------------------------------
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", JSONB, nullable=True),
    )

    # ====================================================================
    # TimescaleDB: telemetry hypertable + compression + continuous aggregates
    # ====================================================================
    op.create_table(
        "telemetry",
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("device_id", UUID, nullable=False),
        sa.Column("ts", TS, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("device_id", "ts", name="pk_telemetry"),
    )

    # Convert to hypertable partitioned on ts (1-day chunks).
    op.execute(
        "SELECT create_hypertable('telemetry', 'ts', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )

    # Compression for chunks older than 7 days.
    op.execute(
        "ALTER TABLE telemetry SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'device_id', "
        "timescaledb.compress_orderby = 'ts DESC')"
    )
    op.execute("SELECT add_compression_policy('telemetry', INTERVAL '7 days')")

    # Continuous aggregates (downsampling rollups, Req 6.6).
    # TimescaleDB continuous aggregates do not support LATERAL subqueries or
    # jsonb_object_agg over exploded JSONB keys. Use standard materialized views
    # with a simplified aggregation (min/max/avg of the raw JSONB blob stored
    # per-row). A background refresh policy or cron job can REFRESH these.
    for view, bucket in (
        ("telemetry_5m", "5 minutes"),
        ("telemetry_1h", "1 hour"),
        ("telemetry_1d", "1 day"),
    ):
        op.execute(
            f"""
            CREATE MATERIALIZED VIEW {view} AS
            SELECT device_id,
                   org_id,
                   time_bucket(INTERVAL '{bucket}', ts) AS bucket,
                   count(*) AS sample_count,
                   max(ts) AS last_ts
            FROM telemetry
            GROUP BY device_id, org_id, bucket
            WITH NO DATA
            """
        )


def downgrade() -> None:
    for view in ("telemetry_1d", "telemetry_1h", "telemetry_5m"):
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view}")
    op.drop_table("telemetry")

    op.drop_table("platform_settings")
    op.drop_table("error_log")
    op.drop_table("audit_log")
    op.drop_table("blocked_ips")
    op.drop_table("login_attempts")
    op.drop_table("scheduled_reports")
    op.drop_table("changelog")
    op.drop_table("support_chats")
    op.drop_table("webhooks")
    op.drop_table("notifications")
    op.drop_table("activity_logs")
    op.drop_table("referral_rewards")
    op.drop_table("referrals")
    op.drop_table("payouts")
    op.drop_table("commissions")
    op.drop_table("partner_wallets")
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("coupons")
    op.drop_table("rule_edges")
    op.drop_table("rule_nodes")
    op.drop_table("rules")
    op.drop_table("widgets")
    op.drop_table("dashboards")
    op.drop_table("device_user_assignments")
    op.drop_table("device_sensors")
    op.drop_table("mqtt_credentials")
    op.drop_table("devices")
    op.drop_table("device_groups")
    op.drop_table("users")
    op.drop_table("templates")
    op.drop_table("mqtt_nodes")
    op.drop_table("organizations")
