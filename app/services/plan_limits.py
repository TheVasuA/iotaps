"""Subscription plan limits (Task 14.1, Req 15.1, 15.2, 15.7).

Single source of truth for the per-plan entitlements the platform enforces:

    Free_Plan : 2 Devices, 20000 telemetry messages/month, 7 days retention,
                10 sensors, 2 Rules, view-only device access (Req 15.1).
    Pro_Plan  : unlimited Devices, unlimited messages, 20 sensors,
                unlimited Rules, full device control (Req 15.2).

These limits are referenced by the device-provisioning guard (device count),
the sensor/rule guards, the Message_Quota counter (``app.services.quota_service``),
the Data_Retention worker (retention days), and the control surface (view-only
vs full control). Centralising them here keeps every enforcement point in sync
and gives the "ambiguous plan falls back to Free" rule (Req 15.7) one home.

A plan value that is not recognised as Pro - ``None``, empty, or any unexpected
string - resolves to the (most restrictive) Free limits so we never grant a
Pro benefit by accident (Req 15.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.errors import AppError

# Canonical plan identifiers (organizations.plan).
FREE_PLAN = "free"
PRO_PLAN = "pro"


class PlanLimitError(AppError):
    """Raised when an action would exceed the organization's plan allowance.

    Returned as HTTP 403 with a stable ``plan_limit_exceeded`` code so the
    frontend can branch on it and surface an upgrade prompt (Req 15.x).
    """

    error_code = "plan_limit_exceeded"
    status_code = 403


@dataclass(frozen=True)
class PlanLimits:
    """The entitlements granted by one subscription plan.

    A ``None`` value for a numeric limit means *unlimited* (Pro). ``full_control``
    distinguishes Pro's full device control from the Free plan's view-only
    access (Req 15.1, 15.2).
    """

    plan: str
    # Maximum provisioned devices; None = unlimited (Req 15.1, 15.2).
    max_devices: Optional[int]
    # Telemetry messages permitted per billing month; None = unlimited.
    max_messages_per_month: Optional[int]
    # Days of telemetry retained (drives the Data_Retention worker, Req 15.1).
    retention_days: int
    # Maximum sensors across the org's devices; None = unlimited.
    max_sensors: Optional[int]
    # Maximum active Rules; None = unlimited (Req 15.1, 15.2; see rule_service).
    max_rules: Optional[int]
    # Whether the plan grants device control (Pro) or is view-only (Free).
    full_control: bool


# Free retains everything for 7 days and is view-only (Req 15.1).
FREE_LIMITS = PlanLimits(
    plan=FREE_PLAN,
    max_devices=2,
    max_messages_per_month=20000,
    retention_days=7,
    max_sensors=10,
    max_rules=2,
    full_control=False,
)

# Pro lifts the device/message/rule caps, allows 20 sensors, and grants full
# device control (Req 15.2). ``retention_days`` is the raw-telemetry window
# (3 months); the hourly-rollup year window is handled by the retention worker.
PRO_LIMITS = PlanLimits(
    plan=PRO_PLAN,
    max_devices=None,
    max_messages_per_month=None,
    retention_days=90,
    max_sensors=20,
    max_rules=None,
    full_control=True,
)

_PLAN_LIMITS: dict[str, PlanLimits] = {
    FREE_PLAN: FREE_LIMITS,
    PRO_PLAN: PRO_LIMITS,
}

# Unknown/ambiguous plans fall back to the most restrictive (Free) entitlements
# so an unclassifiable plan never grants a Pro benefit (Req 15.7).
DEFAULT_LIMITS = FREE_LIMITS


def limits_for_plan(plan: Optional[str]) -> PlanLimits:
    """Resolve the :class:`PlanLimits` for a plan string.

    Matching is case-insensitive and whitespace-tolerant; anything not
    recognised as Pro resolves to the Free limits (Req 15.7).
    """
    if isinstance(plan, str):
        normalized = plan.strip().lower()
        if normalized in _PLAN_LIMITS:
            return _PLAN_LIMITS[normalized]
    return DEFAULT_LIMITS


def is_metered(plan: Optional[str]) -> bool:
    """Whether telemetry volume is capped under ``plan`` (Free/ambiguous = True).

    Pro has an unlimited message allowance, so its telemetry is never metered
    against a quota; every other plan (including ambiguous ones) is (Req 15.2,
    15.3, 15.7).
    """
    return limits_for_plan(plan).max_messages_per_month is not None


def has_full_control(plan: Optional[str]) -> bool:
    """Whether ``plan`` grants full device control (Pro) vs view-only (Free)."""
    return limits_for_plan(plan).full_control
