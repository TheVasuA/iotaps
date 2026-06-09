"""Referral program tracking and reward tiers (Task 17.1, Req 19).

Implements the referral surface from design.md ("Billing, Partner, Referral"):

    GET /referrals -> {code, count, rewards[]}

and the signup-time referral recording that feeds it.

Design / requirement mapping:

- **Record on signup (Req 19.1).** When a referred friend registers with a
  referral code, :func:`record_referral` resolves the code to the referring
  user and inserts a ``referrals`` row (status ``confirmed``) plus sets the new
  user's ``referred_by``.
- **Reward tiers (Req 19.2-19.4).** :func:`reward_for_referral_count` is the
  pure tier table: 1 referral grants 1 device for 1 month, 2 grant 2 devices for
  1 month, 6 grant 3 devices for 3 months. Tiers are *thresholds* - the highest
  reached tier wins.
- **Cap (Req 19.5).** The total grant is clamped to 3 devices / 3 months, so no
  amount of referrals exceeds the cap (and the 6+ tier already sits at it).
- **One account per Gmail identity (Req 19.6).** ``referrals.referred_gmail`` is
  UNIQUE; :func:`record_referral` also pre-checks so a second sign-up from the
  same Gmail cannot be counted twice.
- **No payment required (Req 19.7).** Rewards are derived purely from the
  confirmed-referral count - the grant path never inspects payments or
  subscriptions, so a referred friend never has to pay for the referrer to earn.

A referrer holds at most one ``referral_rewards`` row representing their current
total grant; it is upserted as their referral count crosses tiers, which keeps
the cap trivially enforced and the grant idempotent.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.organization import Organization
from app.models.referral import Referral, ReferralReward
from app.models.user import User

logger = get_logger(__name__)

# Referral reward caps (Req 19.5): no user earns more than this in total.
CAP_DEVICES = 3
CAP_MONTHS = 3

# A confirmed referral is one that counts toward reward tiers (Req 19.1). The
# referred friend never has to pay, so a recorded referral is confirmed
# immediately on signup (Req 19.7).
STATUS_CONFIRMED = "confirmed"

# Approximate days-per-month used only to derive a reward ``expires_at`` from the
# granted month count; the reward magnitude (devices/months) is exact.
_DAYS_PER_MONTH = 30


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def reward_for_referral_count(count: int) -> tuple[int, int]:
    """Resolve a confirmed-referral ``count`` to a (devices, months) grant.

    Tier thresholds (Req 19.2-19.4), highest reached tier wins:

        >= 6 referrals -> 3 devices for 3 months
        >= 2 referrals -> 2 devices for 1 month
        >= 1 referral  -> 1 device  for 1 month
        0 referrals    -> no reward

    The result is clamped to the cap of 3 devices / 3 months (Req 19.5), so the
    function never returns a grant larger than the cap regardless of ``count``.
    """
    if count < 0:
        count = 0
    if count >= 6:
        devices, months = 3, 3
    elif count >= 2:
        devices, months = 2, 1
    elif count >= 1:
        devices, months = 1, 1
    else:
        devices, months = 0, 0
    # Cap (Req 19.5): never exceed 3 devices / 3 months.
    return min(devices, CAP_DEVICES), min(months, CAP_MONTHS)


def generate_referral_code() -> str:
    """Generate a short, URL-safe referral code (uppercased uuid4 fragment)."""
    return uuid.uuid4().hex[:8].upper()


def _normalize_gmail(value: Optional[str]) -> Optional[str]:
    """Normalise a Gmail/email identity for one-per-identity comparison (Req 19.6)."""
    if not value:
        return None
    return value.strip().lower()


async def ensure_referral_code(session: AsyncSession, org: Organization) -> str:
    """Return the org's referral code, generating and persisting one if absent.

    The referral code lives on the organization (``organizations.referral_code``
    UNIQUE) and is what a user shares to refer friends.
    """
    if org.referral_code:
        return org.referral_code
    org.referral_code = generate_referral_code()
    await session.flush()
    return org.referral_code


async def _resolve_referrer(
    session: AsyncSession, referral_code: str
) -> Optional[User]:
    """Resolve a referral code to the referring user.

    The code identifies an organization (``organizations.referral_code``); the
    referrer is that org's earliest-created user (its founding account).
    """
    code = referral_code.strip()
    if not code:
        return None
    org = (
        await session.execute(
            select(Organization).where(Organization.referral_code == code)
        )
    ).scalar_one_or_none()
    if org is None:
        return None
    referrer = (
        await session.execute(
            select(User)
            .where(User.org_id == org.id)
            .order_by(User.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return referrer


async def _count_confirmed_referrals(
    session: AsyncSession, referrer_user_id: uuid.UUID
) -> int:
    """Count a referrer's confirmed referrals (Req 19.1 basis for tiers)."""
    result = await session.execute(
        select(func.count())
        .select_from(Referral)
        .where(
            Referral.referrer_user_id == referrer_user_id,
            Referral.status == STATUS_CONFIRMED,
        )
    )
    return int(result.scalar_one() or 0)


async def _upsert_reward(
    session: AsyncSession, referrer_user_id: uuid.UUID, count: int
) -> Optional[ReferralReward]:
    """Create/update the referrer's single reward row for their current tier.

    Computes the capped (devices, months) grant for ``count`` and stores it on
    the referrer's one ``referral_rewards`` row. Returns ``None`` when the count
    earns no reward yet.
    """
    devices, months = reward_for_referral_count(count)
    reward = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer_user_id
            )
        )
    ).scalar_one_or_none()

    if devices == 0:
        return reward  # nothing earned yet; leave any existing row untouched

    now = _now()
    expires_at = now + datetime.timedelta(days=_DAYS_PER_MONTH * months)
    if reward is None:
        reward = ReferralReward(
            referrer_user_id=referrer_user_id,
            devices_granted=devices,
            months_granted=months,
            granted_at=now,
            expires_at=expires_at,
        )
        session.add(reward)
    else:
        reward.devices_granted = devices
        reward.months_granted = months
        reward.granted_at = now
        reward.expires_at = expires_at
    await session.flush()
    return reward


async def record_referral(
    session: AsyncSession,
    *,
    referral_code: str,
    referred_user: User,
    referred_gmail: Optional[str] = None,
) -> Optional[Referral]:
    """Record a signup referral and (re)grant the referrer's reward (Req 19.1-19.7).

    Resolves ``referral_code`` to the referring user, inserts a confirmed
    ``referrals`` row, links ``referred_user.referred_by``, and upserts the
    referrer's reward for their new confirmed-referral count.

    Enforces one referral per Gmail identity (Req 19.6): a Gmail that has
    already been referred is rejected. A code that cannot be resolved, or a
    self-referral, is rejected. No payment is consulted (Req 19.7).

    Returns the created :class:`Referral`, or raises :class:`ValidationError`
    for an invalid/duplicate referral.

    The caller is responsible for committing the surrounding transaction.
    """
    referrer = await _resolve_referrer(session, referral_code)
    if referrer is None:
        raise ValidationError(
            "Referral code is not valid", error_code="referral_code_invalid"
        )
    if referrer.id == referred_user.id:
        raise ValidationError(
            "You cannot refer yourself", error_code="referral_self"
        )

    gmail = _normalize_gmail(referred_gmail or referred_user.email)

    # One referral account per Gmail identity (Req 19.6): reject a Gmail that has
    # already been recorded as a referred friend.
    if gmail is not None:
        existing = (
            await session.execute(
                select(Referral.id).where(Referral.referred_gmail == gmail)
            )
        ).first()
        if existing is not None:
            raise ValidationError(
                "This account has already been referred",
                error_code="referral_gmail_used",
            )

    referral = Referral(
        referrer_user_id=referrer.id,
        referred_user_id=referred_user.id,
        referred_gmail=gmail,
        status=STATUS_CONFIRMED,
    )
    session.add(referral)
    referred_user.referred_by = referrer.id
    await session.flush()

    count = await _count_confirmed_referrals(session, referrer.id)
    await _upsert_reward(session, referrer.id, count)

    logger.info(
        "referral_recorded",
        extra={"referrer_user_id": str(referrer.id), "count": count},
    )
    return referral


async def get_referral_summary(
    session: AsyncSession, user_id: Any
) -> dict[str, Any]:
    """Build the GET /referrals payload for a user: {code, count, rewards[]}.

    ``code`` is the user's shareable referral code (generated on first read if
    absent), ``count`` is their confirmed-referral total, and ``rewards`` lists
    their granted referral rewards (Req 19.1, 19.2).
    """
    try:
        user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    except (ValueError, TypeError) as exc:
        raise ValidationError("Invalid user id") from exc

    user = await session.get(User, user_uuid)
    if user is None:
        raise NotFoundError("User not found")

    org = await session.get(Organization, user.org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    code = await ensure_referral_code(session, org)

    count = await _count_confirmed_referrals(session, user_uuid)

    rewards = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == user_uuid
            )
        )
    ).scalars().all()

    return {
        "code": code,
        "count": count,
        "rewards": [
            {
                "devices_granted": r.devices_granted,
                "months_granted": r.months_granted,
                "granted_at": r.granted_at.isoformat() if r.granted_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rewards
        ],
    }
