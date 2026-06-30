"""Admin operations API: health, errors, security, settings (Task 20.5).

Super_Admin-only operational surface from design.md ("Admin", Req 28-29):

    GET   /admin/health      -> [service statuses]                  (Req 28.1)
    GET   /admin/errors      -> {recent, trends}                    (Req 28.3)
    GET   /admin/security    -> {login_attempts, blocked_ips, audit_log}  (Req 29.2)
    PATCH /admin/settings    {pricing?, jwt_expiry?, ...} -> {settings}    (Req 29.4)
    GET   /admin/settings    -> {settings}                          (Req 29.4)
    GET   /admin/resources   -> {storage, ram, cdn}                 (Req 29.1)
    GET   /admin/backups     -> {snapshot controls}                 (Req 29.6)
    GET   /admin/marketing   -> {lead_pipeline, marketing_tools}    (Req 29.5)

Error recording (Req 28.2, 28.4) and IP blocking on repeated failed logins
(Req 29.3) are implemented in :mod:`app.services.admin_ops_service` and consumed
by the platform's error handlers / auth flow respectively; this router exposes
the read/admin surface over that data.

Every route requires the Super_Admin role (Req 2.5).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.core.security.deps import require_role
from app.core.security.principal import ROLE_SUPER_ADMIN, Principal
from app.db.session import get_session
from app.services import admin_ops_service


def _db_conn_params() -> dict[str, str]:
    """Parse the SQLAlchemy ``database_url`` into libpq connection parameters.

    Strips the async driver suffix (``+asyncpg``) and URL-decodes credentials so
    they can be handed to ``pg_dump`` / ``pg_restore``. The password is returned
    separately and passed via the ``PGPASSWORD`` env var (never on the command
    line) to avoid leaking it in the process list.
    """
    raw = get_settings().database_url
    raw = raw.replace("+asyncpg", "").replace("+psycopg2", "").replace("+psycopg", "")
    parsed = urlparse(raw)
    return {
        "user": unquote(parsed.username or "iotaps"),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "postgres",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/iotaps").lstrip("/") or "iotaps",
    }

router = APIRouter(prefix="/admin", tags=["admin", "ops"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ServiceStatus(BaseModel):
    name: str
    status: str  # ok | degraded | unconfigured


class HealthResponse(BaseModel):
    services: list[ServiceStatus]


class ErrorEntry(BaseModel):
    id: str
    error_code: str | None = None
    message: str
    user_id: str | None = None
    org_id: str | None = None
    device_id: str | None = None
    detail: dict | None = None
    created_at: str | None = None


class ErrorTrendPoint(BaseModel):
    date: str
    count: int


class ErrorsResponse(BaseModel):
    recent: list[ErrorEntry]
    trends: list[ErrorTrendPoint]


class LoginAttemptEntry(BaseModel):
    id: str
    ip: str | None = None
    email: str | None = None
    success: bool
    created_at: str | None = None


class BlockedIpEntry(BaseModel):
    id: str
    ip: str
    reason: str | None = None
    blocked_until: str | None = None
    created_at: str | None = None


class AuditLogEntry(BaseModel):
    id: str
    actor_user_id: str | None = None
    action: str
    detail: dict | None = None
    created_at: str | None = None


class SecurityResponse(BaseModel):
    login_attempts: list[LoginAttemptEntry]
    blocked_ips: list[BlockedIpEntry]
    audit_log: list[AuditLogEntry]


class SettingsUpdateRequest(BaseModel):
    """Platform settings to apply platform-wide immediately (Req 29.4).

    Free-form key/value updates - pricing, plan limits, JWT expiry, rate limits,
    2FA policy, themes, etc. At least one key is required.
    """

    updates: dict[str, Any] = Field(
        ..., description="Setting key -> value pairs to apply", min_length=1
    )

    model_config = {"extra": "forbid"}


class SettingsResponse(BaseModel):
    settings: dict[str, Any]


# ---------------------------------------------------------------------------
# Health (Req 28.1)
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse)
async def admin_health(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> HealthResponse:
    """Return the status of each platform service (Req 28.1)."""
    statuses = await admin_ops_service.service_statuses(session)
    return HealthResponse(services=[ServiceStatus(**s) for s in statuses])


# ---------------------------------------------------------------------------
# Live system stats (RAM, disk, CPU, connections)
# ---------------------------------------------------------------------------
@router.get("/system-stats")
async def admin_system_stats(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Return live system stats (RAM, disk, MQTT connections)."""
    from app.workers.stats_publisher import (
        _get_memory_stats, _get_disk_stats, _calc_cpu_percent,
        _get_mqtt_connections, _get_redis_info, _get_ingest_queue_size,
    )
    from app.core.redis_client import get_redis
    redis = get_redis()
    memory = _get_memory_stats()
    disk = _get_disk_stats()
    cpu = _calc_cpu_percent()
    connections = await _get_mqtt_connections(redis) if redis else 0
    redis_info = await _get_redis_info(redis) if redis else {}
    queue = await _get_ingest_queue_size(redis) if redis else 0
    return {
        "ram": memory,
        "disk": disk,
        "cpu_percent": cpu,
        "mqtt_connections": connections,
        "redis_memory": redis_info,
        "ingest_queue_size": queue,
        "max_connections_design": 10000,
    }


# ---------------------------------------------------------------------------
# Errors (Req 28.3)
# ---------------------------------------------------------------------------
@router.get("/errors", response_model=ErrorsResponse)
async def admin_errors(
    limit: int = Query(default=50, ge=1, le=500),
    days: int = Query(default=7, ge=1, le=90),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> ErrorsResponse:
    """Return recent errors and error trends over time (Req 28.3)."""
    recent = await admin_ops_service.recent_errors(session, limit=limit)
    trends = await admin_ops_service.error_trends(session, days=days)
    return ErrorsResponse(
        recent=[ErrorEntry(**e) for e in recent],
        trends=[ErrorTrendPoint(**t) for t in trends],
    )


# ---------------------------------------------------------------------------
# Security (Req 29.2)
# ---------------------------------------------------------------------------
@router.get("/security", response_model=SecurityResponse)
async def admin_security(
    limit: int = Query(default=50, ge=1, le=500),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> SecurityResponse:
    """Return login attempts, blocked IPs, and the audit log (Req 29.2)."""
    data = await admin_ops_service.security_overview(session, limit=limit)
    return SecurityResponse(
        login_attempts=[LoginAttemptEntry(**a) for a in data["login_attempts"]],
        blocked_ips=[BlockedIpEntry(**b) for b in data["blocked_ips"]],
        audit_log=[AuditLogEntry(**a) for a in data["audit_log"]],
    )


# ---------------------------------------------------------------------------
# Settings (Req 29.4)
# ---------------------------------------------------------------------------
@router.get("/settings", response_model=SettingsResponse)
async def get_admin_settings(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> SettingsResponse:
    """Return all current platform settings (Req 29.4)."""
    return SettingsResponse(settings=await admin_ops_service.all_settings())


@router.patch("/settings", response_model=SettingsResponse)
async def patch_admin_settings(
    payload: SettingsUpdateRequest,
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> SettingsResponse:
    """Apply platform settings platform-wide immediately (Req 29.4).

    Each provided setting is written through the settings loader, whose
    read-through Redis cache makes the change effective across every stateless
    app server at once. Returns all settings after applying the updates.
    """
    await admin_ops_service.apply_settings(payload.updates)
    return SettingsResponse(settings=await admin_ops_service.all_settings())


# ---------------------------------------------------------------------------
# Resources / backups / marketing (Req 29.1, 29.5, 29.6)
# ---------------------------------------------------------------------------
@router.get("/resources")
async def admin_resources(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict[str, Any]:
    """Return storage, RAM, and CDN/Cloudflare management controls (Req 29.1)."""
    return await admin_ops_service.resource_controls()


@router.get("/backups")
async def admin_backups(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict[str, Any]:
    """Return Contabo snapshot backup controls (Req 29.6)."""
    return await admin_ops_service.backup_controls()


@router.get("/marketing")
async def admin_marketing(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the enterprise lead pipeline and marketing tools (Req 29.5)."""
    return await admin_ops_service.marketing_overview(session)


# ---------------------------------------------------------------------------
# Platform quick controls
# ---------------------------------------------------------------------------
@router.post("/platform/flush-cache")
async def flush_cache(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Flush the Redis cache (clears settings cache, sessions, telemetry cache)."""
    from app.core.redis_client import get_redis
    redis = get_redis()
    if redis:
        await redis.flushdb()
    return {"status": "ok", "message": "Redis cache flushed"}


@router.post("/platform/toggle-maintenance")
async def toggle_maintenance(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Toggle platform maintenance mode."""
    from app.core.redis_client import get_redis
    redis = get_redis()
    if redis:
        current = await redis.get("iotaps:maintenance_mode")
        new_val = "0" if current and current != b"0" else "1"
        await redis.set("iotaps:maintenance_mode", new_val)
        return {"status": "ok", "maintenance_mode": new_val == "1"}
    return {"status": "error", "message": "Redis unavailable"}


@router.post("/platform/disconnect-ws")
async def disconnect_ws(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Publish a disconnect signal to all WebSocket clients."""
    from app.core.redis_client import get_redis
    redis = get_redis()
    if redis:
        await redis.publish("iotaps:ws:disconnect_all", "1")
    return {"status": "ok", "message": "Disconnect signal sent"}


@router.post("/platform/backup")
async def trigger_backup(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Create a database backup on the VPS disk (pg_dump, custom format).

    Writes a compressed ``.dump`` to ``/srv/backups`` inside the container. For
    a copy you can download to your own machine instead, use
    ``GET /admin/platform/backup/download``.
    """
    params = _db_conn_params()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = "/srv/backups"
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"iotaps_backup_{timestamp}.dump")

    env = {**os.environ, "PGPASSWORD": params["password"]}
    cmd = [
        "pg_dump",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "-Fc",  # custom format -> restorable with pg_restore, compressed
        "-f", backup_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
    )
    _, stderr = await proc.communicate()

    if proc.returncode == 0:
        size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
        return {"status": "ok", "path": backup_path, "size_bytes": size}
    raise HTTPException(status_code=500, detail=stderr.decode()[:300] or "backup failed")


@router.get("/platform/backup/download")
async def download_backup(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> FileResponse:
    """Run pg_dump and stream the backup file to the admin's browser.

    The dump is written to a temp file, streamed as an octet-stream download,
    then deleted once the response has been sent (Req 29.6).
    """
    params = _db_conn_params()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fd, tmp_path = tempfile.mkstemp(prefix=f"iotaps_{timestamp}_", suffix=".dump")
    os.close(fd)

    env = {**os.environ, "PGPASSWORD": params["password"]}
    cmd = [
        "pg_dump",
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "-Fc",
        "-f", tmp_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0 or not os.path.exists(tmp_path):
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(
            status_code=500, detail=stderr.decode()[:300] or "backup failed"
        )

    filename = f"iotaps_backup_{timestamp}.dump"
    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(os.unlink, tmp_path),
    )


@router.post("/platform/restore")
async def restore_backup(
    file: UploadFile = File(...),
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Restore the database from an uploaded pg_dump (.dump) file.

    DESTRUCTIVE: existing objects are dropped and recreated from the dump
    (``pg_restore --clean --if-exists``). Intended for disaster recovery only;
    the caller (admin UI) confirms with the operator before invoking this.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".dump")
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        params = _db_conn_params()
        env = {**os.environ, "PGPASSWORD": params["password"]}
        cmd = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "-h", params["host"],
            "-p", params["port"],
            "-U", params["user"],
            "-d", params["dbname"],
            tmp_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
        _, stderr = await proc.communicate()
        warnings = stderr.decode()

        if proc.returncode != 0:
            # pg_restore exits non-zero on ignorable "does not exist, skipping"
            # notices from --clean. Treat as success-with-warnings unless there
            # are hard errors.
            hard_errors = [
                line
                for line in warnings.splitlines()
                if "error:" in line.lower() and "does not exist" not in line.lower()
            ]
            if hard_errors:
                raise HTTPException(
                    status_code=500,
                    detail="; ".join(hard_errors)[:500] or "restore failed",
                )
        return {"status": "ok", "message": "Database restored", "warnings": warnings[:500]}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Identity vault (MongoDB off-VPS mirror)
# ---------------------------------------------------------------------------
@router.get("/platform/vault/status")
async def vault_status(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
) -> dict:
    """Return MongoDB identity-vault connection status and document counts."""
    from app.services import identity_vault

    return await identity_vault.status()


@router.post("/platform/vault/sync")
async def vault_sync(
    _: Principal = Depends(require_role(ROLE_SUPER_ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trigger an immediate full identity re-sync into the MongoDB vault."""
    from app.services import identity_vault

    if not get_settings().mongodb_enabled:
        raise HTTPException(status_code=400, detail="MongoDB vault is not configured")
    return await identity_vault.resync_all(session)
