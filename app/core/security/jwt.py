"""JWT access-token issuance/verification and refresh-token lifecycle (Req 1).

This module implements the Auth_Service token mechanics described in design.md
("JWT claims structure"):

Access token claims (Req 1, 2, 3)::

    {
      "sub": "user_uuid",
      "org_id": "org_uuid",
      "role": "super_admin|project_center|device_user",
      "iat": 1700000000,
      "exp": 1700000900,
      "jti": "token_id"
    }

Refresh tokens are *opaque* server-side records: a random ``jti`` is signed into
a long-lived JWT handed to the client, while the authoritative record lives in
Redis under ``refresh:{jti}`` (Req 1.5/1.6). Revocation = deleting that key;
rotation = deleting the old key and issuing a new one. A refresh token is only
honoured if its ``jti`` is still present in Redis, so logout (Req 1.6) and
rotation (Req 1.4) invalidate prior tokens, and expired/revoked tokens are
rejected (Req 1.5).

The functions here are storage-agnostic where possible: Redis operations accept
an injected async client so they can be unit/property tested with a fake Redis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt

from app.core.config import Settings, get_settings
from app.core.redis_keys import refresh_token_key

# Token type markers carried in the ``typ`` claim to prevent an access token
# from being used where a refresh token is expected and vice versa.
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

VALID_ROLES = frozenset({"super_admin", "project_center", "device_user"})


class TokenError(Exception):
    """Raised when a token is malformed, expired, of the wrong type, or revoked."""


@dataclass(frozen=True)
class AccessClaims:
    """Decoded access-token claims (the request principal source)."""

    sub: str
    org_id: str
    role: str
    iat: int
    exp: int
    jti: str

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Access tokens (Req 1.1, 1.2, 1.4)
# ---------------------------------------------------------------------------
def create_access_token(
    *,
    user_id: str,
    org_id: str,
    role: str,
    email: str = "",
    settings: Settings | None = None,
    now: datetime | None = None,
    jti: str | None = None,
) -> str:
    """Issue a signed, short-lived access JWT with the standard claim set."""
    settings = settings or get_settings()
    issued = now or _now()
    iat = _epoch(issued)
    exp = iat + int(settings.jwt_access_token_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "email": email,
        "iat": iat,
        "exp": exp,
        "jti": jti or uuid.uuid4().hex,
        "typ": ACCESS_TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings | None = None) -> AccessClaims:
    """Verify signature/expiry and return the access-token claims.

    Raises ``TokenError`` for an invalid signature, expired token, wrong token
    type, or missing required claims (Req 1.3 surface for protected routes).
    """
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("access token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid access token") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("not an access token")
    try:
        return AccessClaims(
            sub=str(payload["sub"]),
            org_id=str(payload["org_id"]),
            role=str(payload["role"]),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            jti=str(payload["jti"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("access token missing required claims") from exc


# ---------------------------------------------------------------------------
# Refresh tokens (Req 1.4, 1.5, 1.6) - server-side record in refresh:{jti}
# ---------------------------------------------------------------------------
def _create_refresh_jwt(
    *,
    jti: str,
    user_id: str,
    org_id: str,
    role: str,
    settings: Settings,
    now: datetime,
) -> str:
    iat = _epoch(now)
    exp = iat + int(settings.jwt_refresh_token_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "iat": iat,
        "exp": exp,
        "jti": jti,
        "typ": REFRESH_TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def issue_refresh_token(
    redis,
    *,
    user_id: str,
    org_id: str,
    role: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> str:
    """Create a refresh token and persist its authoritative record in Redis.

    The record lives at ``refresh:{jti}`` with a TTL equal to the refresh-token
    lifetime so it auto-expires (Req 1.5). The returned JWT embeds the same
    ``jti``; a refresh is only honoured while this key exists.
    """
    settings = settings or get_settings()
    issued = now or _now()
    jti = uuid.uuid4().hex
    token = _create_refresh_jwt(
        jti=jti,
        user_id=user_id,
        org_id=org_id,
        role=role,
        settings=settings,
        now=issued,
    )
    if redis is not None:
        await redis.set(
            refresh_token_key(jti),
            str(user_id),
            ex=int(settings.jwt_refresh_token_ttl_seconds),
        )
    return token


def _decode_refresh_jwt(token: str, settings: Settings) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("refresh token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid refresh token") from exc
    if payload.get("typ") != REFRESH_TOKEN_TYPE:
        raise TokenError("not a refresh token")
    return payload


async def revoke_refresh_token(redis, token: str, *, settings: Settings | None = None) -> bool:
    """Revoke a refresh token by deleting its ``refresh:{jti}`` record (Req 1.6).

    Returns ``True`` if a record was removed. A malformed/expired token simply
    yields ``False`` (idempotent logout).
    """
    settings = settings or get_settings()
    try:
        payload = _decode_refresh_jwt(token, settings)
    except TokenError:
        return False
    if redis is None:
        return False
    removed = await redis.delete(refresh_token_key(payload["jti"]))
    return bool(removed)


async def rotate_refresh_token(
    redis,
    token: str,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Validate a refresh token and rotate it, returning new (access, refresh).

    Steps (Req 1.4, 1.5):
      1. Decode + verify the refresh JWT (signature/expiry/type).
      2. Confirm its ``jti`` still exists in Redis (not revoked) - else reject.
      3. Delete the old record (one-time use) and issue a fresh refresh token.
      4. Mint a new access token.

    Raises ``TokenError`` if the token is expired, revoked, or otherwise
    invalid, requiring the client to re-authenticate (Req 1.5).
    """
    settings = settings or get_settings()
    payload = _decode_refresh_jwt(token, settings)
    jti = payload["jti"]

    if redis is None:
        raise TokenError("refresh store unavailable")

    # Only honour tokens whose server-side record is still present (Req 1.5/1.6).
    exists = await redis.delete(refresh_token_key(jti))
    if not exists:
        raise TokenError("refresh token revoked or expired")

    user_id = str(payload["sub"])
    org_id = str(payload.get("org_id", ""))
    role = str(payload.get("role", ""))
    email = str(payload.get("email", ""))

    access = create_access_token(
        user_id=user_id, org_id=org_id, role=role, email=email, settings=settings, now=now
    )
    new_refresh = await issue_refresh_token(
        redis,
        user_id=user_id,
        org_id=org_id,
        role=role,
        settings=settings,
        now=now,
    )
    return access, new_refresh
