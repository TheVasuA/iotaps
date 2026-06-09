"""Unit tests for JWT issuance, refresh rotation, and revocation (Task 2.3, Req 1).

These cover the token mechanics in ``app.core.security.jwt``:
  - access-token claim round-trip {sub, org_id, role, iat, exp, jti} (Req 1.1)
  - rejecting tampered / wrong-type / expired tokens (Req 1.3, 1.5)
  - refresh issuance stores a ``refresh:{jti}`` record (Req 1.4-1.6)
  - rotation returns new tokens and invalidates the old refresh (Req 1.4)
  - revocation (logout) removes the record (Req 1.6)
  - a rotated/revoked/expired refresh is rejected (Req 1.5)

A fake in-memory Redis (fakeredis) backs the refresh store - no live Redis.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import jwt as pyjwt
import pytest

from app.core.config import Settings
from app.core.redis_keys import refresh_token_key
from app.core.security import jwt as jwt_service


def _settings() -> Settings:
    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=900,
        jwt_refresh_token_ttl_seconds=3600,
    )


def _fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------
def test_access_token_claims_round_trip():
    settings = _settings()
    token = jwt_service.create_access_token(
        user_id="u1", org_id="o1", role="project_center", settings=settings
    )
    claims = jwt_service.decode_access_token(token, settings=settings)
    assert claims.sub == "u1"
    assert claims.org_id == "o1"
    assert claims.role == "project_center"
    assert claims.jti  # present and non-empty
    assert claims.exp - claims.iat == settings.jwt_access_token_ttl_seconds


def test_access_token_rejects_bad_signature():
    settings = _settings()
    token = jwt_service.create_access_token(
        user_id="u1", org_id="o1", role="device_user", settings=settings
    )
    other = Settings(jwt_secret="different-secret", jwt_algorithm="HS256")
    with pytest.raises(jwt_service.TokenError):
        jwt_service.decode_access_token(token, settings=other)


def test_access_token_rejects_expired():
    settings = _settings()
    past = datetime.now(timezone.utc) - timedelta(seconds=settings.jwt_access_token_ttl_seconds + 10)
    token = jwt_service.create_access_token(
        user_id="u1", org_id="o1", role="device_user", settings=settings, now=past
    )
    with pytest.raises(jwt_service.TokenError):
        jwt_service.decode_access_token(token, settings=settings)


def test_access_token_rejects_refresh_token_type():
    settings = _settings()
    # Forge a token with the refresh type marker; decode_access_token must reject.
    payload = {
        "sub": "u1", "org_id": "o1", "role": "device_user",
        "iat": 1700000000, "exp": 9999999999, "jti": "x",
        "typ": jwt_service.REFRESH_TOKEN_TYPE,
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt_service.TokenError):
        jwt_service.decode_access_token(token, settings=settings)


def test_super_admin_flag():
    settings = _settings()
    token = jwt_service.create_access_token(
        user_id="u1", org_id="o1", role="super_admin", settings=settings
    )
    claims = jwt_service.decode_access_token(token, settings=settings)
    assert claims.is_super_admin is True


# ---------------------------------------------------------------------------
# Refresh tokens: issue / revoke / rotate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_issue_refresh_stores_record():
    settings = _settings()
    redis = _fake_redis()
    token = await jwt_service.issue_refresh_token(
        redis, user_id="u1", org_id="o1", role="project_center", settings=settings
    )
    payload = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert payload["typ"] == jwt_service.REFRESH_TOKEN_TYPE
    # Server-side record exists for the jti.
    assert await redis.get(refresh_token_key(payload["jti"])) == "u1"


@pytest.mark.asyncio
async def test_revoke_refresh_removes_record():
    settings = _settings()
    redis = _fake_redis()
    token = await jwt_service.issue_refresh_token(
        redis, user_id="u1", org_id="o1", role="device_user", settings=settings
    )
    payload = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    assert await jwt_service.revoke_refresh_token(redis, token, settings=settings) is True
    assert await redis.get(refresh_token_key(payload["jti"])) is None
    # Idempotent: second revoke is a no-op returning False.
    assert await jwt_service.revoke_refresh_token(redis, token, settings=settings) is False


@pytest.mark.asyncio
async def test_rotate_returns_new_tokens_and_invalidates_old():
    settings = _settings()
    redis = _fake_redis()
    refresh = await jwt_service.issue_refresh_token(
        redis, user_id="u1", org_id="o1", role="project_center", settings=settings
    )
    access, new_refresh = await jwt_service.rotate_refresh_token(
        redis, refresh, settings=settings
    )
    # New access token carries the same identity.
    claims = jwt_service.decode_access_token(access, settings=settings)
    assert claims.sub == "u1" and claims.org_id == "o1" and claims.role == "project_center"
    # The old refresh token is now rejected (one-time use, Req 1.4/1.5).
    with pytest.raises(jwt_service.TokenError):
        await jwt_service.rotate_refresh_token(redis, refresh, settings=settings)
    # The new refresh token still works.
    access2, _ = await jwt_service.rotate_refresh_token(redis, new_refresh, settings=settings)
    assert jwt_service.decode_access_token(access2, settings=settings).sub == "u1"


@pytest.mark.asyncio
async def test_rotate_rejects_revoked_token():
    settings = _settings()
    redis = _fake_redis()
    refresh = await jwt_service.issue_refresh_token(
        redis, user_id="u1", org_id="o1", role="device_user", settings=settings
    )
    await jwt_service.revoke_refresh_token(redis, refresh, settings=settings)
    with pytest.raises(jwt_service.TokenError):
        await jwt_service.rotate_refresh_token(redis, refresh, settings=settings)


@pytest.mark.asyncio
async def test_rotate_rejects_expired_refresh():
    settings = _settings()
    redis = _fake_redis()
    past = datetime.now(timezone.utc) - timedelta(
        seconds=settings.jwt_refresh_token_ttl_seconds + 10
    )
    refresh = await jwt_service.issue_refresh_token(
        redis, user_id="u1", org_id="o1", role="device_user", settings=settings, now=past
    )
    with pytest.raises(jwt_service.TokenError):
        await jwt_service.rotate_refresh_token(redis, refresh, settings=settings)
