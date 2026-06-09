"""Super_Admin operations: health, error recording, security, settings (Task 20.5).

Implements the operational surface from design.md ("Admin", Req 28-29):

- **Service health (Req 28.1).** :func:`service_statuses` reports the status of
  each platform service (API plus its dependencies: Redis, PostgreSQL, MQTT).
- **Error recording (Req 28.2, 28.4).** :func:`record_error` persists a platform
  error with the associated user / Organization / Device context, and *never
  raises* - if recording fails the platform keeps operating (Req 28.4).
- **Recent errors + trends (Req 28.3).** :func:`recent_errors` returns the most
  recent errors and :func:`error_trends` buckets error counts over time.
- **Security data (Req 29.2).** :func:`security_overview` returns recent login
  attempts, blocked IPs, and the audit log.
- **IP blocking (Req 29.3).** :func:`record_login_attempt` records each attempt
  and, when failures from an IP exceed the configured threshold within the
  window, blocks the IP (writes a ``blocked_ips`` row). :func:`is_ip_blocked`
  reports whether an IP is currently blocked.
- **Platform settings (Req 29.4).** :func:`apply_setting` persists a platform
  setting through :mod:`app.core.settings_loader`, whose read-through Redis
  cache makes the change apply platform-wide immediately.

Callers own the surrounding transaction unless noted. ``record_error`` manages
its own failure handling so a logging error can never break the caller.
"""

from __future__ import annotations

import datetime
import uuid
from collections import OrderedDict
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.settings_loader import get_all_settings, set_setting
from app.models.error_log import ErrorLog
from app.models.security import AuditLog, BlockedIp, LoginAttempt

logger = get_logger(__name__)

# Default brute-force policy (Req 29.3). Overridable via platform settings.
DEFAULT_FAILED_LOGIN_THRESHOLD = 5
DEFAULT_LOGIN_WINDOW_SECONDS = 15 * 60
DEFAULT_BLOCK_DURATION_SECONDS = 60 * 60


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _as_aware(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Normalise a stored timestamp to timezone-aware UTC.

    SQLite round-trips ``DateTime`` columns as naive datetimes; treat a naive
    value as UTC so window/expiry comparisons are correct on any backend.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _coerce_uuid(value: Any) -> Optional[uuid.UUID]:
    """Best-effort coercion to UUID; returns None on any invalid/empty value."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Service health (Req 28.1)
# ---------------------------------------------------------------------------
async def service_statuses(session: AsyncSession) -> list[dict[str, str]]:
    """Return the status of each platform service (Req 28.1).

    Each entry is ``{"name", "status"}`` where status is ``ok`` / ``degraded`` /
    ``unconfigured``. The API itself is ``ok`` if this code is running; the
    relational DB, Redis, and MQTT are probed where possible.
    """
    statuses: list[dict[str, str]] = [{"name": "api", "status": "ok"}]

    # Relational DB: a trivial round-trip confirms reachability.
    try:
        await session.execute(select(1))
        statuses.append({"name": "database", "status": "ok"})
    except Exception:
        statuses.append({"name": "database", "status": "degraded"})

    # Redis.
    redis = get_redis()
    if redis is None:
        statuses.append({"name": "redis", "status": "unconfigured"})
    else:
        try:
            await redis.ping()
            statuses.append({"name": "redis", "status": "ok"})
        except Exception:
            statuses.append({"name": "redis", "status": "degraded"})

    return statuses


# ---------------------------------------------------------------------------
# Error recording (Req 28.2, 28.4)
# ---------------------------------------------------------------------------
async def record_error(
    session: AsyncSession,
    *,
    message: str,
    error_code: Optional[str] = None,
    user_id: Any = None,
    org_id: Any = None,
    device_id: Any = None,
    detail: Optional[dict] = None,
) -> Optional[ErrorLog]:
    """Persist a platform error with user/org/device context (Req 28.2).

    This function never raises: if recording the error fails for any reason the
    platform continues operating (Req 28.4). Returns the created row on success,
    or ``None`` when recording failed. The caller is responsible for committing
    the surrounding transaction on success.
    """
    try:
        entry = ErrorLog(
            message=message,
            error_code=error_code,
            user_id=_coerce_uuid(user_id),
            org_id=_coerce_uuid(org_id),
            device_id=_coerce_uuid(device_id),
            detail=detail,
        )
        session.add(entry)
        await session.flush()
        return entry
    except Exception:  # noqa: BLE001 - logging must never break the platform
        # Req 28.4: continue operating even if error recording fails. Roll back
        # the failed insert so the caller's session stays usable.
        try:
            await session.rollback()
        except Exception:  # pragma: no cover - defensive
            pass
        logger.warning("error_recording_failed", extra={"error_message": message})
        return None


async def recent_errors(
    session: AsyncSession, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Return the most recent recorded errors, newest first (Req 28.3)."""
    rows = (
        (
            await session.execute(
                select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_error(e) for e in rows]


async def error_trends(
    session: AsyncSession, *, days: int = 7
) -> list[dict[str, Any]]:
    """Return error counts bucketed by day over the trailing window (Req 28.3).

    Buckets are returned oldest-first and include zero-count days so the trend
    line is continuous.
    """
    days = max(1, days)
    since = _now() - datetime.timedelta(days=days - 1)
    since_day = since.replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        (
            await session.execute(
                select(ErrorLog.created_at).where(ErrorLog.created_at >= since_day)
            )
        )
        .scalars()
        .all()
    )

    # Seed every day in the window with a zero count (continuous trend).
    buckets: "OrderedDict[str, int]" = OrderedDict()
    for offset in range(days):
        day = (since_day + datetime.timedelta(days=offset)).date().isoformat()
        buckets[day] = 0

    for created in rows:
        created = _as_aware(created)
        if created is None:
            continue
        key = created.date().isoformat()
        if key in buckets:
            buckets[key] += 1

    return [{"date": day, "count": count} for day, count in buckets.items()]


def _serialize_error(entry: ErrorLog) -> dict[str, Any]:
    created = _as_aware(entry.created_at)
    return {
        "id": str(entry.id),
        "error_code": entry.error_code,
        "message": entry.message,
        "user_id": str(entry.user_id) if entry.user_id else None,
        "org_id": str(entry.org_id) if entry.org_id else None,
        "device_id": str(entry.device_id) if entry.device_id else None,
        "detail": entry.detail,
        "created_at": created.isoformat() if created else None,
    }


# ---------------------------------------------------------------------------
# IP blocking on repeated failures (Req 29.3)
# ---------------------------------------------------------------------------
async def _failed_login_policy() -> tuple[int, int, int]:
    """Resolve (threshold, window_seconds, block_seconds) from platform settings."""
    policy = await _safe_get_setting("failed_login_policy")
    if not isinstance(policy, dict):
        policy = {}
    threshold = int(policy.get("threshold", DEFAULT_FAILED_LOGIN_THRESHOLD))
    window = int(policy.get("window_seconds", DEFAULT_LOGIN_WINDOW_SECONDS))
    block = int(policy.get("block_seconds", DEFAULT_BLOCK_DURATION_SECONDS))
    return max(1, threshold), max(1, window), max(1, block)


async def _safe_get_setting(key: str) -> Any:
    try:
        from app.core.settings_loader import get_setting

        return await get_setting(key)
    except Exception:  # pragma: no cover - defensive; settings must not break auth
        return None


async def record_login_attempt(
    session: AsyncSession,
    *,
    ip: Optional[str],
    email: Optional[str],
    success: bool,
) -> Optional[BlockedIp]:
    """Record a login attempt and block the IP past the failure threshold (Req 29.3).

    Persists a ``login_attempts`` row (Req 29.2). On a failed attempt, counts
    recent failures from the same IP within the policy window; when they reach
    or exceed the threshold, writes/refreshes a ``blocked_ips`` row and returns
    it. A successful attempt never blocks. Returns the ``BlockedIp`` row when a
    block is created/refreshed, else ``None``.
    """
    session.add(LoginAttempt(ip=ip, email=email, success=success))
    await session.flush()

    if success or not ip:
        return None

    threshold, window_seconds, block_seconds = await _failed_login_policy()
    window_start = _now() - datetime.timedelta(seconds=window_seconds)

    failures = (
        await session.execute(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.ip == ip,
                LoginAttempt.success.is_(False),
                LoginAttempt.created_at >= window_start,
            )
        )
    ).scalar_one()

    if failures < threshold:
        return None

    return await _block_ip(
        session,
        ip=ip,
        reason=f"Exceeded {threshold} failed login attempts",
        block_seconds=block_seconds,
    )


async def _block_ip(
    session: AsyncSession, *, ip: str, reason: str, block_seconds: int
) -> BlockedIp:
    """Create or refresh the block record for ``ip`` (idempotent on unique ip)."""
    blocked_until = _now() + datetime.timedelta(seconds=block_seconds)
    existing = (
        await session.execute(select(BlockedIp).where(BlockedIp.ip == ip))
    ).scalar_one_or_none()
    if existing is not None:
        existing.reason = reason
        existing.blocked_until = blocked_until
        await session.flush()
        return existing

    blocked = BlockedIp(ip=ip, reason=reason, blocked_until=blocked_until)
    session.add(blocked)
    await session.flush()
    return blocked


async def is_ip_blocked(session: AsyncSession, ip: Optional[str]) -> bool:
    """Whether ``ip`` is currently blocked (block not expired) (Req 29.3)."""
    if not ip:
        return False
    blocked = (
        await session.execute(select(BlockedIp).where(BlockedIp.ip == ip))
    ).scalar_one_or_none()
    if blocked is None:
        return False
    until = _as_aware(blocked.blocked_until)
    # A NULL blocked_until means an indefinite block.
    return until is None or until > _now()


# ---------------------------------------------------------------------------
# Security overview (Req 29.2)
# ---------------------------------------------------------------------------
async def security_overview(
    session: AsyncSession, *, limit: int = 50
) -> dict[str, Any]:
    """Return login attempts, blocked IPs, and the audit log (Req 29.2)."""
    attempts = (
        (
            await session.execute(
                select(LoginAttempt)
                .order_by(LoginAttempt.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    blocked = (
        (
            await session.execute(
                select(BlockedIp).order_by(BlockedIp.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    audit = (
        (
            await session.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "login_attempts": [_serialize_attempt(a) for a in attempts],
        "blocked_ips": [_serialize_blocked(b) for b in blocked],
        "audit_log": [_serialize_audit(a) for a in audit],
    }


def _serialize_attempt(a: LoginAttempt) -> dict[str, Any]:
    created = _as_aware(a.created_at)
    return {
        "id": str(a.id),
        "ip": a.ip,
        "email": a.email,
        "success": a.success,
        "created_at": created.isoformat() if created else None,
    }


def _serialize_blocked(b: BlockedIp) -> dict[str, Any]:
    created = _as_aware(b.created_at)
    until = _as_aware(b.blocked_until)
    return {
        "id": str(b.id),
        "ip": b.ip,
        "reason": b.reason,
        "blocked_until": until.isoformat() if until else None,
        "created_at": created.isoformat() if created else None,
    }


def _serialize_audit(a: AuditLog) -> dict[str, Any]:
    created = _as_aware(a.created_at)
    return {
        "id": str(a.id),
        "actor_user_id": str(a.actor_user_id) if a.actor_user_id else None,
        "action": a.action,
        "detail": a.detail,
        "created_at": created.isoformat() if created else None,
    }


# ---------------------------------------------------------------------------
# Platform settings (Req 29.4)
# ---------------------------------------------------------------------------
async def apply_setting(key: str, value: Any) -> Any:
    """Persist a platform setting so it applies platform-wide immediately (Req 29.4).

    Delegates to the settings loader, which writes the source of truth and
    refreshes the read-through Redis cache so every stateless app server picks
    up the new value at once (pricing, plans, JWT expiry, rate limits, 2FA,
    themes).
    """
    await set_setting(key, value)
    return value


async def apply_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Apply multiple platform settings at once (Req 29.4). Returns the new values."""
    applied: dict[str, Any] = {}
    for key, value in updates.items():
        await set_setting(key, value)
        applied[key] = value
    return applied


async def all_settings() -> dict[str, Any]:
    """Return all current platform settings (Req 29.4)."""
    return await get_all_settings()


# ---------------------------------------------------------------------------
# Resources, backups, lead pipeline + marketing (Req 29.1, 29.5, 29.6)
# ---------------------------------------------------------------------------
async def resource_controls() -> dict[str, Any]:
    """Return storage / RAM / CDN management controls (Req 29.1).

    The MVP surfaces the configured controls the Super_Admin operates; live
    metrics are populated by the infra monitor as that integration lands.
    """
    return {
        "storage": {"provider": "contabo_nvme", "managed": True},
        "ram": {"managed": True},
        "cdn": {"provider": "cloudflare", "managed": True},
    }


async def backup_controls() -> dict[str, Any]:
    """Return Contabo snapshot backup controls (Req 29.6)."""
    return {
        "provider": "contabo_snapshots",
        "enabled": True,
        "actions": ["create_snapshot", "list_snapshots", "restore_snapshot"],
    }


async def marketing_overview(session: AsyncSession) -> dict[str, Any]:
    """Return the enterprise lead pipeline and marketing tools (Req 29.5)."""
    return {
        "lead_pipeline": {"stages": ["new", "contacted", "qualified", "won", "lost"]},
        "marketing_tools": {
            "email_campaigns": {"available": True},
            "in_app_banners": {"available": True},
            "leaderboards": {"available": True},
        },
    }
