"""Identity Vault — best-effort mirror of critical identity data to MongoDB.

Mirrors the data you cannot afford to lose — user logins (email, role,
**password hashes**), device credentials (device id, token, ACL), and device
records — into a MongoDB database (e.g. a free MongoDB Atlas 512MB cluster).

Why:
  * The mirror is hosted **off the VPS**, so a complete server loss never takes
    the identity data with it. Unlike the R2 dump, it's a live, queryable copy.
  * Postgres stays the single source of truth. This is a *secondary* mirror,
    written after the Postgres commit and wrapped so it can NEVER break a login,
    registration, or device action. On recovery you still restore from the
    Postgres backup; the vault is an independent safety copy / verification.

Security:
  * Only password **hashes** (argon2) are mirrored — never plaintext passwords.
  * Device tokens are mirrored because the token *is* the device identity; treat
    the Atlas cluster as sensitive (network allow-list + a strong DB user).

Design:
  * Dependency-light: uses ``pymongo`` (sync) run in a worker thread via
    ``asyncio.to_thread``, matching the email service pattern. No-op when
    ``MONGODB_URI`` is unset.
  * The backbone is :func:`resync_all` (a full upsert sweep run periodically by
    the vault worker) so every identity row is mirrored without hooking every
    mutation path. Real-time helpers (:func:`mirror_device`, etc.) keep the
    most security-relevant records fresh between sweeps.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Collection names in the vault database.
COL_USERS = "users"
COL_CREDENTIALS = "device_credentials"
COL_DEVICES = "devices"

_OP_TIMEOUT = 10  # seconds per Mongo operation

# Cached client (pymongo MongoClient is thread-safe and lazy-connects).
_client: Any = None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def _get_client() -> Any:
    global _client
    settings = get_settings()
    if not settings.mongodb_enabled:
        return None
    if _client is None:
        from pymongo import MongoClient

        _client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            appname="iotaps-identity-vault",
        )
    return _client


def _db() -> Any:
    client = _get_client()
    return None if client is None else client[get_settings().mongodb_db]


# ---------------------------------------------------------------------------
# Document builders (pure)
# ---------------------------------------------------------------------------
def _user_doc(user: Any) -> dict:
    return {
        "_id": str(user.id),
        "org_id": str(user.org_id) if getattr(user, "org_id", None) else None,
        "email": user.email,
        "role": user.role,
        # Password HASH only (argon2/bcrypt) — never plaintext.
        "password_hash": getattr(user, "password_hash", None),
        "password_format": getattr(user, "password_format", None),
        "oauth_provider": getattr(user, "oauth_provider", None),
        "twofa_enabled": bool(getattr(user, "twofa_enabled", False)),
        "twofa_secret": getattr(user, "twofa_secret", None),
    }


def _credential_doc(cred: Any) -> dict:
    return {
        "_id": str(cred.id),
        "org_id": str(cred.org_id) if getattr(cred, "org_id", None) else None,
        "device_id": str(cred.device_id) if getattr(cred, "device_id", None) else None,
        "token": getattr(cred, "token", None),
        "username": getattr(cred, "username", None),
        "password_hash": getattr(cred, "password_hash", None),
        "acl_pattern": getattr(cred, "acl_pattern", None),
        "revoked": bool(getattr(cred, "revoked", False)),
    }


def _device_doc(device: Any) -> dict:
    return {
        "_id": str(device.id),
        "org_id": str(device.org_id) if getattr(device, "org_id", None) else None,
        "device_uid": getattr(device, "device_uid", None),
        "label": getattr(device, "label", None),
        "node_id": str(device.node_id) if getattr(device, "node_id", None) else None,
        "status": getattr(device, "status", None),
    }


# ---------------------------------------------------------------------------
# Low-level sync helpers (run in a thread)
# ---------------------------------------------------------------------------
def _upsert_sync(collection: str, doc: dict) -> None:
    db = _db()
    if db is None:
        return
    db[collection].update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)


def _delete_sync(collection: str, doc_id: str) -> None:
    db = _db()
    if db is None:
        return
    db[collection].delete_one({"_id": doc_id})


def _bulk_upsert_sync(collection: str, docs: list[dict]) -> int:
    db = _db()
    if db is None or not docs:
        return 0
    from pymongo import UpdateOne

    ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in docs]
    result = db[collection].bulk_write(ops, ordered=False)
    return int((result.upserted_count or 0) + (result.modified_count or 0))


def _status_sync() -> dict:
    db = _db()
    if db is None:
        return {"enabled": False, "connected": False}
    # ping verifies the connection is actually reachable.
    db.client.admin.command("ping")
    return {
        "enabled": True,
        "connected": True,
        "database": get_settings().mongodb_db,
        "counts": {
            COL_USERS: db[COL_USERS].estimated_document_count(),
            COL_CREDENTIALS: db[COL_CREDENTIALS].estimated_document_count(),
            COL_DEVICES: db[COL_DEVICES].estimated_document_count(),
        },
    }


# ---------------------------------------------------------------------------
# Async wrappers — all best-effort, never raise
# ---------------------------------------------------------------------------
async def _run(fn, *args) -> Any:
    if not get_settings().mongodb_enabled:
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=_OP_TIMEOUT)
    except Exception:  # noqa: BLE001 - mirror must never break the caller
        logger.warning("identity_vault_op_failed", exc_info=True)
        return None


async def mirror_user(user: Any) -> None:
    await _run(_upsert_sync, COL_USERS, _user_doc(user))


async def mirror_credential(cred: Any) -> None:
    await _run(_upsert_sync, COL_CREDENTIALS, _credential_doc(cred))


async def mirror_device(device: Any) -> None:
    await _run(_upsert_sync, COL_DEVICES, _device_doc(device))


async def remove_device(device_id: str) -> None:
    await _run(_delete_sync, COL_DEVICES, str(device_id))


async def remove_credentials_for_device(cred_ids: list[str]) -> None:
    for cid in cred_ids:
        await _run(_delete_sync, COL_CREDENTIALS, str(cid))


# ---------------------------------------------------------------------------
# Full re-sync (the backbone) + status
# ---------------------------------------------------------------------------
async def resync_all(session: AsyncSession) -> dict:
    """Upsert every identity row (users, credentials, devices) into the vault.

    Returns a small summary dict. Identity data is tiny relative to telemetry,
    so a full sweep is cheap and guarantees the mirror is complete regardless of
    which code paths created the rows.
    """
    if not get_settings().mongodb_enabled:
        return {"enabled": False, "synced": {}}

    from app.models.device import Device, MqttCredential
    from app.models.user import User

    users = (await session.execute(select(User))).scalars().all()
    creds = (await session.execute(select(MqttCredential))).scalars().all()
    devices = (await session.execute(select(Device))).scalars().all()

    user_n = await _run(_bulk_upsert_sync, COL_USERS, [_user_doc(u) for u in users]) or 0
    cred_n = await _run(_bulk_upsert_sync, COL_CREDENTIALS, [_credential_doc(c) for c in creds]) or 0
    dev_n = await _run(_bulk_upsert_sync, COL_DEVICES, [_device_doc(d) for d in devices]) or 0

    summary = {COL_USERS: user_n, COL_CREDENTIALS: cred_n, COL_DEVICES: dev_n}
    logger.info("identity_vault_resync", extra=summary)
    return {"enabled": True, "synced": summary}


async def status() -> dict:
    """Return vault connection status + per-collection document counts."""
    if not get_settings().mongodb_enabled:
        return {"enabled": False, "connected": False}
    result = await _run(_status_sync)
    return result or {"enabled": True, "connected": False}
