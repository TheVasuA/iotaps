"""Property-based test for referral reward tiers and caps (Task 17.2, Req 19).

# Feature: iotaps-platform, Property 14: Referral reward tiers are correct and capped

Property 14 (design.md "Correctness Properties"):

    For any number of confirmed referrals, the granted Referral_Reward follows
    the tier mapping (>=1 -> 1 device/1 month, >=2 -> 2 devices/1 month, >=6 ->
    3 devices/3 months), is non-decreasing in referral count, and never exceeds
    3 devices for 3 months; and for any Gmail identity, at most one referral
    account is eligible.

Validates: Requirements 19.2, 19.3, 19.4, 19.5, 19.6

The tier table :func:`reward_for_referral_count` is a pure function (no
DB/Redis), so the tier/cap/monotonicity properties call it directly. The
one-per-Gmail-identity property (Req 19.6) is exercised against an in-memory
SQLite async engine that seeds a referrer and replays signup referrals,
mirroring ``test_node_assignment_property.py``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import ValidationError
from app.core.security.principal import ROLE_PROJECT_CENTER
from app.db.base import Base
from app.models.organization import Organization
from app.models.referral import Referral, ReferralReward
from app.models.user import User
from app.services.referral_service import (
    CAP_DEVICES,
    CAP_MONTHS,
    record_referral,
    reward_for_referral_count,
)

# ---------------------------------------------------------------------------
# Reference tier table derived straight from the Req 19.2-19.5 acceptance
# criteria. Highest reached threshold wins; result is capped at 3 devices /
# 3 months.
# ---------------------------------------------------------------------------


def _expected_reward(count: int) -> tuple[int, int]:
    """Reference (devices, months) grant for a confirmed-referral ``count``."""
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
    return min(devices, CAP_DEVICES), min(months, CAP_MONTHS)


# Counts span well below 0 through past the top (>=6) tier so every band, the
# 0/1, 1/2, and 5/6 boundaries, and the open-ended top tier are exercised.
_count = st.integers(min_value=-3, max_value=200)


@settings(max_examples=30, deadline=None)
@given(count=_count)
def test_reward_tiers_are_correct_and_capped(count: int) -> None:
    """Property 14: tier mapping is correct and capped at 3 devices/3 months.

    Validates: Requirements 19.2, 19.3, 19.4, 19.5
    """
    devices, months = reward_for_referral_count(count)

    # (a) Correctness: the grant matches the tier the count falls in (Req 19.2-19.4).
    assert (devices, months) == _expected_reward(count)

    # (b) Cap: no count ever earns more than 3 devices / 3 months (Req 19.5).
    assert devices <= CAP_DEVICES
    assert months <= CAP_MONTHS

    # (c) Grants are never negative.
    assert devices >= 0 and months >= 0


@settings(max_examples=30, deadline=None)
@given(data=st.data())
def test_reward_is_monotonically_non_decreasing(data: st.DataObject) -> None:
    """A larger referral count never yields a smaller grant (Req 19.2-19.5).

    Validates: Requirements 19.2, 19.3, 19.4, 19.5
    """
    smaller = data.draw(st.integers(min_value=0, max_value=200))
    larger = data.draw(st.integers(min_value=smaller, max_value=200))

    dev_s, mon_s = reward_for_referral_count(smaller)
    dev_l, mon_l = reward_for_referral_count(larger)

    # Both dimensions are non-decreasing as the referral count grows.
    assert dev_l >= dev_s
    assert mon_l >= mon_s


def test_tier_boundaries_are_exact() -> None:
    """The 0/1, 1/2, and 5/6 thresholds each step to the next tier exactly.

    Validates: Requirements 19.2, 19.3, 19.4
    """
    assert reward_for_referral_count(0) == (0, 0)
    assert reward_for_referral_count(1) == (1, 1)
    assert reward_for_referral_count(2) == (2, 1)
    assert reward_for_referral_count(5) == (2, 1)
    assert reward_for_referral_count(6) == (3, 3)


# ---------------------------------------------------------------------------
# One referral account per Gmail identity (Req 19.6), exercised against an
# in-memory SQLite async engine.
# ---------------------------------------------------------------------------

_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Referral.__table__,
    ReferralReward.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Swap the Postgres ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


_prepare_tables_for_sqlite()


# A Gmail identity drawn from a small pool so collisions (the case the
# one-per-identity rule must reject) occur frequently.
_gmail = st.sampled_from(
    ["a@gmail.com", "b@gmail.com", "c@gmail.com", "d@gmail.com"]
)


@st.composite
def _signup_sequence(draw: st.DrawFn) -> list[str]:
    """A sequence of referred-friend Gmail identities signing up under one code."""
    return draw(st.lists(_gmail, min_size=1, max_size=12))


async def _seed_referrer(session: AsyncSession) -> str:
    """Create the referring org + user, return the shared referral code."""
    org = Organization(name="Referrer Co", referral_code="REFCODE1")
    session.add(org)
    await session.flush()
    referrer = User(
        org_id=org.id,
        email="referrer@example.com",
        role=ROLE_PROJECT_CENTER,
    )
    session.add(referrer)
    await session.flush()
    return org.referral_code


async def _run_gmail_identity(gmails: list[str]) -> None:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES)
            )
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            code = await _seed_referrer(session)

            accepted_gmails: set[str] = set()
            for i, gmail in enumerate(gmails):
                # Each friend is a distinct user account; only the Gmail
                # identity may repeat across the sequence.
                friend = User(
                    org_id=(
                        await session.execute(select(Organization.id))
                    ).scalar_one(),
                    email=f"friend{i}@example.com",
                    role=ROLE_PROJECT_CENTER,
                )
                session.add(friend)
                await session.flush()

                already_used = gmail in accepted_gmails
                if already_used:
                    # A Gmail that was already referred must be rejected (Req 19.6).
                    with pytest.raises(ValidationError) as exc:
                        await record_referral(
                            session,
                            referral_code=code,
                            referred_user=friend,
                            referred_gmail=gmail,
                        )
                    assert exc.value.error_code == "referral_gmail_used"
                    # Roll back the failed unit so the session stays usable.
                    await session.rollback()
                else:
                    await record_referral(
                        session,
                        referral_code=code,
                        referred_user=friend,
                        referred_gmail=gmail,
                    )
                    await session.commit()
                    accepted_gmails.add(gmail)

            # Each accepted Gmail identity appears exactly once in referrals.
            rows = (
                await session.execute(
                    select(Referral.referred_gmail).where(
                        Referral.referred_gmail.is_not(None)
                    )
                )
            ).scalars().all()
            assert len(rows) == len(set(rows)), "a Gmail identity was counted twice"
            assert set(rows) == accepted_gmails

            # The reward reflects only the unique, confirmed referrals and stays
            # within the cap (Req 19.5).
            count = (
                await session.execute(
                    select(func.count()).select_from(Referral)
                )
            ).scalar_one()
            assert count == len(accepted_gmails)

            reward = (
                await session.execute(select(ReferralReward))
            ).scalar_one_or_none()
            expected = _expected_reward(len(accepted_gmails))
            if expected == (0, 0):
                assert reward is None
            else:
                assert reward is not None
                assert (reward.devices_granted, reward.months_granted) == expected
                assert reward.devices_granted <= CAP_DEVICES
                assert reward.months_granted <= CAP_MONTHS
    finally:
        await engine.dispose()


# Feature: iotaps-platform, Property 14: Referral reward tiers are correct and capped
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(gmails=_signup_sequence())
def test_one_referral_account_per_gmail_identity(gmails: list[str]) -> None:
    """Property 14: at most one referral account is eligible per Gmail identity.

    Validates: Requirement 19.6
    """
    asyncio.run(_run_gmail_identity(gmails))
