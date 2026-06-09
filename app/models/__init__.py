"""ORM models for the IoTAPS relational + time-series schema (design.md Table Catalog).

Importing this package registers every model on ``Base.metadata`` so Alembic
autogeneration and ``create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.billing import (
    Commission,
    Coupon,
    PartnerWallet,
    Payment,
    Payout,
    Subscription,
)
from app.models.dashboard import Dashboard, Widget
from app.models.device import (
    Device,
    DeviceGroup,
    DeviceSensor,
    DeviceUserAssignment,
    MqttCredential,
)
from app.models.error_log import ErrorLog
from app.models.infra import MqttNode, PlatformSetting, Template
from app.models.ops import (
    ActivityLog,
    Changelog,
    Notification,
    ScheduledReport,
    SupportChat,
    Webhook,
)
from app.models.organization import Organization
from app.models.referral import Referral, ReferralReward
from app.models.rule import Rule, RuleEdge, RuleNode
from app.models.security import AuditLog, BlockedIp, LoginAttempt
from app.models.telemetry import Telemetry
from app.models.user import User

__all__ = [
    "Base",
    # organization / user
    "Organization",
    "User",
    # device domain
    "Device",
    "DeviceGroup",
    "DeviceSensor",
    "DeviceUserAssignment",
    "MqttCredential",
    # dashboards
    "Dashboard",
    "Widget",
    # rules
    "Rule",
    "RuleNode",
    "RuleEdge",
    # billing
    "Subscription",
    "Payment",
    "Coupon",
    "PartnerWallet",
    "Commission",
    "Payout",
    # referral
    "Referral",
    "ReferralReward",
    # infra / platform
    "MqttNode",
    "Template",
    "PlatformSetting",
    # ops
    "ActivityLog",
    "Notification",
    "Webhook",
    "SupportChat",
    "Changelog",
    "ScheduledReport",
    # security
    "LoginAttempt",
    "BlockedIp",
    "AuditLog",
    # error log
    "ErrorLog",
    # telemetry (hypertable)
    "Telemetry",
]
