"""Property-based tests for JWT token mechanics (Task 2.4, Req 1.1, 1.4-1.6).

Uses Hypothesis to exercise :mod:`app.core.security.jwt` across a wide range of
user identities and refresh-token lifecycle outcomes, validating Property 3:
access-token claim round-trip and rejection of revoked/expired refresh tokens.

A fresh in-memory ``fakeredis`` instance backs the refresh store per example, so
no live Redis is required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.config import Settings
from app.core.security import jwt as jwt_service


def _settings() -> Settings:
    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=900,
        jwt_refresh_token_ttl_seconds=3600,
    )


# Identity fields are opaque non-empty strings (uuids/role names in production).
# A wide character set stresses claim encoding/decoding while staying within the
# valid input space (the issuer ``str()``-coerces these values).
_ids = st.text(min_size=1, max_size=64)
_roles = st.sampled_from(sorted(jwt_service.VALID_ROLES))

# How an issued refresh token is invalidated before the refresh attempt:
#   "revoke"  -> explicit logout (Req 1.6)
#   "rotate"  -> prior rotation consumed the one-time token (Req 1.4)
#   "expired" -> token issued in the past, beyond its TTL (Req 1.5)
_invalidations = st.sampled_from(["revoke", "rotate", "expired"])


# Feature: iotaps-platform, Property 3: JWT claims round-trip and refresh revocation
@given(user_id=_ids, org_id=_ids, role=_roles, invalidation=_invalidations)
@settings(max_examples=30, deadline=None)
def test_jwt_round_trip_and_refresh_revocation(
    user_id: str, org_id: str, role: str, invalidation: str
):
    """Validates: Requirements 1.1, 1.4, 1.5, 1.6.

    For any user:
      * encoding a JWT and decoding it preserves ``sub``, ``org_id``, ``role``
        (access-token claim round-trip, Req 1.1); and
      * for any refresh token whose ``jti`` has been revoked (Req 1.6), rotated
        away (Req 1.4), or expired (Req 1.5), the refresh request is rejected.
    """
    settings_obj = _settings()

    # --- Access-token claim round-trip (Req 1.1) ---------------------------
    access = jwt_service.create_access_token(
        user_id=user_id, org_id=org_id, role=role, settings=settings_obj
    )
    claims = jwt_service.decode_access_token(access, settings=settings_obj)
    assert claims.sub == user_id
    assert claims.org_id == org_id
    assert claims.role == role

    # --- Refresh revocation / expiry rejection (Req 1.4, 1.5, 1.6) ---------
    async def _refresh_scenario() -> None:
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        if invalidation == "expired":
            # Issued far enough in the past that the embedded JWT exp has passed.
            past = datetime.now(timezone.utc) - timedelta(
                seconds=settings_obj.jwt_refresh_token_ttl_seconds + 60
            )
            refresh = await jwt_service.issue_refresh_token(
                redis, user_id=user_id, org_id=org_id, role=role,
                settings=settings_obj, now=past,
            )
        else:
            refresh = await jwt_service.issue_refresh_token(
                redis, user_id=user_id, org_id=org_id, role=role,
                settings=settings_obj,
            )
            if invalidation == "revoke":
                # Explicit logout removes the server-side record (Req 1.6).
                assert await jwt_service.revoke_refresh_token(
                    redis, refresh, settings=settings_obj
                ) is True
            elif invalidation == "rotate":
                # One rotation consumes the token; the old one must not work again.
                new_access, new_refresh = await jwt_service.rotate_refresh_token(
                    redis, refresh, settings=settings_obj
                )
                # Sanity: the freshly minted access token round-trips identity.
                rotated_claims = jwt_service.decode_access_token(
                    new_access, settings=settings_obj
                )
                assert rotated_claims.sub == user_id
                assert rotated_claims.org_id == org_id
                assert rotated_claims.role == role

        # In every scenario the original refresh token is now invalid and the
        # refresh request must be rejected, forcing re-authentication.
        with pytest.raises(jwt_service.TokenError):
            await jwt_service.rotate_refresh_token(
                redis, refresh, settings=settings_obj
            )

    asyncio.run(_refresh_scenario())
