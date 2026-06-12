"""Redis key and pub/sub channel namespaces for the IoTAPS Cache_Store.

This module is the single source of truth for every Redis key the platform
uses. Centralising the layout here keeps the ingest pipeline, auth service,
quota counter, command queues, rate limiter, and presence tracking consistent
and avoids stringly-typed keys scattered across workers and routes.

Design references:
- Telemetry ingest queue + pub/sub fan-out (design "Data Stores", Req 6.1-6.4)
- Refresh-token store ``refresh:{jti}`` (design "JWT claims structure", Req 1.5/1.6)
- Monthly quota counter ``quota:{org}:{yyyymm}`` (design "Message Quota", Req 15.3-15.6)
- Offline command queue ``cmdq:{device}`` (design "Command Flow", Req 9.5/9.6)
- Rate-limit token buckets (design "Middleware stack")
- Online device set + websocket presence (Req 23.1 online count, Req 6.4 delivery)

Only Task 1.4 scope: namespace *definitions*. The MQTT_Listener (5.1),
Batch_Writer (5.2), and auth endpoints (2.x) consume these in later tasks.
"""

from __future__ import annotations

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Key prefixes / separators
# ---------------------------------------------------------------------------
# A single namespace prefix lets us run multiple logical environments against
# one Redis instance and makes bulk inspection (`SCAN MATCH iotaps:*`) trivial.
NAMESPACE = "iotaps"
SEP = ":"


def _key(*parts: str) -> str:
    """Join key parts under the global namespace with the standard separator."""
    return SEP.join((NAMESPACE, *(str(p) for p in parts)))


# ---------------------------------------------------------------------------
# Telemetry ingest queue (Req 6.1, 6.2)
# ---------------------------------------------------------------------------
# The MQTT_Listener LPUSHes validated telemetry payloads here; the Batch_Writer
# drains batches of up to 1000 (larger when the backlog exceeds 1000) and only
# LTRIMs after a successful TimescaleDB commit.
INGEST_QUEUE = _key("ingest", "telemetry")


# ---------------------------------------------------------------------------
# Pub/Sub channels (Req 6.3, 6.4)
# ---------------------------------------------------------------------------
# The Batch_Writer publishes the latest value per device after commit; the
# WebSocket gateway subscribes and pushes to dashboard clients within 1s.
_PUBSUB_TELEMETRY = "telemetry"
_PUBSUB_DEVICE = "device"
_PUBSUB_DASHBOARD = "dashboard"


def telemetry_channel(device_id: str) -> str:
    """Pub/sub channel carrying the latest telemetry value for a device."""
    return _key(_PUBSUB_TELEMETRY, device_id)


def device_channel(device_id: str) -> str:
    """Pub/sub channel for device-scoped events (status, command_status)."""
    return _key(_PUBSUB_DEVICE, device_id)


def dashboard_channel(dashboard_id: str) -> str:
    """Pub/sub channel for dashboard-scoped fan-out to subscribed clients."""
    return _key(_PUBSUB_DASHBOARD, dashboard_id)


def admin_stats_channel() -> str:
    """Pub/sub channel for live system stats (RAM, disk, connections)."""
    return _key("admin", "stats")


# ---------------------------------------------------------------------------
# Refresh-token store: refresh:{jti} (Req 1.5, 1.6)
# ---------------------------------------------------------------------------
# Refresh tokens are stored server-side keyed by their JWT id (jti) so logout
# and rotation can revoke them. TTL is set to the refresh-token lifetime.
def refresh_token_key(jti: str) -> str:
    """Server-side refresh-token record keyed by JWT id (``refresh:{jti}``)."""
    return _key("refresh", jti)


# ---------------------------------------------------------------------------
# Monthly message quota counter: quota:{org}:{yyyymm} (Req 15.3-15.6)
# ---------------------------------------------------------------------------
def quota_key(org_id: str, period: str | datetime | None = None) -> str:
    """Monthly telemetry quota counter ``quota:{org}:{yyyymm}``.

    ``period`` may be a ``yyyymm`` string, a ``datetime`` (UTC month is used),
    or ``None`` to use the current UTC month. The counter is INCR'd per
    telemetry message and given an ``expireat`` of the billing-month end so it
    resets automatically (Req 15.6).
    """
    return _key("quota", org_id, _resolve_period(period))


def _resolve_period(period: str | datetime | None) -> str:
    if period is None:
        period = datetime.now(timezone.utc)
    if isinstance(period, datetime):
        return period.strftime("%Y%m")
    return period


# ---------------------------------------------------------------------------
# Upgrade-prompt channel: upgrade:{org} (Req 15.5)
# ---------------------------------------------------------------------------
# When a Free_Plan org reaches its monthly Message_Quota the quota counter
# publishes an upgrade prompt here; the platform surfaces it to the org's
# operators while telemetry continues to be accepted (Req 15.5).
def upgrade_prompt_channel(org_id: str) -> str:
    """Pub/sub channel carrying upgrade prompts for an organization."""
    return _key("upgrade", org_id)


# ---------------------------------------------------------------------------
# Org plan cache: org:plan:{org} (Req 15.3 - quota metering needs the plan)
# ---------------------------------------------------------------------------
# The MQTT_Listener meters telemetry per the owning org's plan but must not hit
# Postgres on every message. The org's plan is cached here (read-through with a
# short TTL) so quota counting stays cheap and resilient.
def org_plan_key(org_id: str) -> str:
    """Cached subscription plan for an organization (``org:plan:{org}``)."""
    return _key("org", "plan", org_id)


# ---------------------------------------------------------------------------
# Offline command queue: cmdq:{device} (Req 9.5, 9.6)
# ---------------------------------------------------------------------------
# Commands issued to an offline device are RPUSHed here and flushed on
# reconnect. If the queue operation fails the command is rejected (Req 9.5).
def command_queue_key(device_id: str) -> str:
    """Offline command queue for a device (``cmdq:{device}``)."""
    return _key("cmdq", device_id)


# ---------------------------------------------------------------------------
# Command status records: cmd:{command_id} (Req 9.4-9.7)
# ---------------------------------------------------------------------------
# Each issued command's status record (type/value/status/timestamps) is stored
# here so ``GET /devices/{id}/commands/{cid}`` can report SENT/QUEUED/
# CONFIRMED/UNACKNOWLEDGED and the ACK handler / timeout can transition it.
def command_record_key(command_id: str) -> str:
    """Status record for a single issued command (``cmd:{command_id}``)."""
    return _key("cmd", command_id)


# ---------------------------------------------------------------------------
# Device command schedules/timers: cmdsched:{device} (Req 9.3)
# ---------------------------------------------------------------------------
# Schedules/timers created for a device are stored in this list so a scheduler
# worker can execute the associated command at the scheduled time.
def command_schedule_key(device_id: str) -> str:
    """Schedule/timer list for a device (``cmdsched:{device}``)."""
    return _key("cmdsched", device_id)


# ---------------------------------------------------------------------------
# Rate-limit token buckets (design "Middleware stack")
# ---------------------------------------------------------------------------
# Token-bucket rate limiting is applied per client IP and per organization.
def rate_limit_ip_key(ip: str) -> str:
    """Rate-limit token bucket for a client IP."""
    return _key("ratelimit", "ip", ip)


def rate_limit_org_key(org_id: str) -> str:
    """Rate-limit token bucket for an organization."""
    return _key("ratelimit", "org", org_id)


# ---------------------------------------------------------------------------
# Online devices + websocket presence (Req 23.1, 6.4)
# ---------------------------------------------------------------------------
# Set of currently-online device ids, maintained from MQTT status (LWT) topic
# transitions. Backs the admin "online devices" count (Req 23.1).
ONLINE_DEVICES = _key("online_devices")


def ws_presence_key(user_id: str) -> str:
    """WebSocket presence record for a connected user/session."""
    return _key("ws", "presence", user_id)


# Set of channel names a websocket session is subscribed to. Used by the
# gateway to route pub/sub messages to the right connections.
def ws_subscriptions_key(session_id: str) -> str:
    """Set of channels a websocket session is subscribed to."""
    return _key("ws", "subs", session_id)
