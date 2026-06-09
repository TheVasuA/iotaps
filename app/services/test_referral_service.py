"""Unit tests for referral tracking and reward tiers (Task 17.1, Req 19).

Uses an in-memory SQLite async session (no live Postgres). Only the tables the
referral path touches are created (``organizations``, ``users``, ``referrals``,
``referral_rewards``), and their Postgres-specific ``gen_random_uuid()`` PK
defaults are swapped for Python uuid4 so SQLite can evaluate them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.core.errors import NotFoundError, ValidationError
from app.db.base import Base
from app.models.organization import Organization
from app.models.referral import Referral, ReferralReward
from app.models.user import User
from app.services import referral_service as rs

_TEST_TABLES = [
    Organization.__table__,
    User.__table__,
    Referral.__table__,
    ReferralReward.__table__,
]


def _prepare_tables_for_sqlite() -> None:
    """Swap each table's ``gen_random_uuid()`` PK default for a Python uuid4."""
    for table in _TEST_TABLES:
        id_col = table.c.id
        id_col.server_default = None
        id_col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture
async def session() -> AsyncSession:
    _prepare_tables_for_sqlite()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TEST_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add_referrer(
    session: AsyncSession, *, code: str = "REFCODE1", email: str = "ref@example.com"
) -> tuple[Organization, User]:
    org = Organization(name="Referrer Org", plan="free", referral_code=code)
    session.add(org)
    await session.flush()
    user = User(
        org_id=org.id,
        email=email,
        gmail_identity=email,
        role="project_center",
    )
    session.add(user)
    await session.flush()
    return org, user


async def _add_new_signup(session: AsyncSession, email: str) -> User:
    """Create a fresh signup (its own org + founding user)."""
    org = Organization(name="New Org", plan="free")
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email=email, gmail_identity=email, role="project_center")
    session.add(user)
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# reward_for_referral_count - pure tier table (Req 19.2-19.5)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "count, expected",
    [
        (0, (0, 0)),
        (1, (1, 1)),  # Req 19.2
        (2, (2, 1)),  # Req 19.3
        (3, (2, 1)),  # still tier-2 until 6
        (5, (2, 1)),
        (6, (3, 3)),  # Req 19.4
        (10, (3, 3)),  # cap holds (Req 19.5)
        (100, (3, 3)),  # cap holds for any count (Req 19.5)
    ],
)
def test_reward_tiers(count, expected):
    assert rs.reward_for_referral_count(count) == expected


def test_reward_never_exceeds_cap():
    for count in range(0, 50):
        devices, months = rs.reward_for_referral_count(count)
        assert devices <= rs.CAP_DEVICES
        assert months <= rs.CAP_MONTHS


# ---------------------------------------------------------------------------
# record_referral (Req 19.1, 19.6, 19.7)
# ---------------------------------------------------------------------------
async def test_record_referral_creates_row_and_links_user(session):
    _, referrer = await _add_referrer(session)
    new_user = await _add_new_signup(session, "friend@example.com")

    referral = await rs.record_referral(
        session,
        referral_code="REFCODE1",
        referred_user=new_user,
        referred_gmail="friend@example.com",
    )

    assert referral.referrer_user_id == referrer.id
    assert referral.referred_user_id == new_user.id
    assert referral.status == rs.STATUS_CONFIRMED
    assert new_user.referred_by == referrer.id


async def test_first_referral_grants_one_device_one_month(session):
    _, referrer = await _add_referrer(session)
    new_user = await _add_new_signup(session, "f1@example.com")

    await rs.record_referral(
        session, referral_code="REFCODE1", referred_user=new_user
    )

    reward = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer.id
            )
        )
    ).scalar_one()
    assert reward.devices_granted == 1
    assert reward.months_granted == 1


async def test_two_referrals_upgrade_reward(session):
    _, referrer = await _add_referrer(session)
    u1 = await _add_new_signup(session, "a@example.com")
    u2 = await _add_new_signup(session, "b@example.com")

    await rs.record_referral(session, referral_code="REFCODE1", referred_user=u1)
    await rs.record_referral(session, referral_code="REFCODE1", referred_user=u2)

    reward = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer.id
            )
        )
    ).scalar_one()
    assert reward.devices_granted == 2
    assert reward.months_granted == 1


async def test_six_referrals_reach_capped_tier(session):
    _, referrer = await _add_referrer(session)
    for i in range(6):
        u = await _add_new_signup(session, f"u{i}@example.com")
        await rs.record_referral(session, referral_code="REFCODE1", referred_user=u)

    reward = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer.id
            )
        )
    ).scalar_one()
    assert reward.devices_granted == 3
    assert reward.months_granted == 3

    # Only one reward row per referrer (upserted, cap holds).
    all_rewards = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer.id
            )
        )
    ).scalars().all()
    assert len(all_rewards) == 1


async def test_one_account_per_gmail_identity(session):
    """A Gmail already referred cannot be counted again (Req 19.6)."""
    await _add_referrer(session)
    u1 = await _add_new_signup(session, "dup@example.com")
    await rs.record_referral(
        session, referral_code="REFCODE1", referred_user=u1, referred_gmail="dup@example.com"
    )

    u2 = await _add_new_signup(session, "dup2@example.com")
    with pytest.raises(ValidationError) as exc:
        await rs.record_referral(
            session,
            referral_code="REFCODE1",
            referred_user=u2,
            referred_gmail="dup@example.com",
        )
    assert exc.value.error_code == "referral_gmail_used"


async def test_gmail_comparison_is_case_insensitive(session):
    await _add_referrer(session)
    u1 = await _add_new_signup(session, "MixedCase@example.com")
    await rs.record_referral(
        session,
        referral_code="REFCODE1",
        referred_user=u1,
        referred_gmail="MixedCase@example.com",
    )
    u2 = await _add_new_signup(session, "other@example.com")
    with pytest.raises(ValidationError):
        await rs.record_referral(
            session,
            referral_code="REFCODE1",
            referred_user=u2,
            referred_gmail="mixedcase@example.com",
        )


async def test_invalid_code_rejected(session):
    new_user = await _add_new_signup(session, "x@example.com")
    with pytest.raises(ValidationError) as exc:
        await rs.record_referral(
            session, referral_code="NOPE", referred_user=new_user
        )
    assert exc.value.error_code == "referral_code_invalid"


async def test_self_referral_rejected(session):
    _, referrer = await _add_referrer(session)
    with pytest.raises(ValidationError) as exc:
        await rs.record_referral(
            session, referral_code="REFCODE1", referred_user=referrer
        )
    assert exc.value.error_code == "referral_self"


async def test_reward_granted_without_payment(session):
    """Reward is derived from referral count alone, no payment needed (Req 19.7)."""
    _, referrer = await _add_referrer(session)
    new_user = await _add_new_signup(session, "nopay@example.com")
    await rs.record_referral(
        session, referral_code="REFCODE1", referred_user=new_user
    )
    # No Payment/Subscription rows exist at all, yet a reward was granted.
    reward = (
        await session.execute(
            select(ReferralReward).where(
                ReferralReward.referrer_user_id == referrer.id
            )
        )
    ).scalar_one()
    assert reward.devices_granted == 1


# ---------------------------------------------------------------------------
# get_referral_summary (Req 19.1, 19.2) -> {code, count, rewards}
# ---------------------------------------------------------------------------
async def test_summary_returns_code_count_rewards(session):
    _, referrer = await _add_referrer(session)
    u1 = await _add_new_signup(session, "s1@example.com")
    u2 = await _add_new_signup(session, "s2@example.com")
    await rs.record_referral(session, referral_code="REFCODE1", referred_user=u1)
    await rs.record_referral(session, referral_code="REFCODE1", referred_user=u2)

    summary = await rs.get_referral_summary(session, referrer.id)
    assert summary["code"] == "REFCODE1"
    assert summary["count"] == 2
    assert len(summary["rewards"]) == 1
    assert summary["rewards"][0]["devices_granted"] == 2
    assert summary["rewards"][0]["months_granted"] == 1


async def test_summary_generates_code_when_absent(session):
    org = Organization(name="No Code Org", plan="free", referral_code=None)
    session.add(org)
    await session.flush()
    user = User(org_id=org.id, email="nc@example.com", role="project_center")
    session.add(user)
    await session.flush()

    summary = await rs.get_referral_summary(session, user.id)
    assert summary["code"]
    assert summary["count"] == 0
    assert summary["rewards"] == []
    # Persisted on the org.
    assert org.referral_code == summary["code"]


async def test_summary_unknown_user_raises(session):
    with pytest.raises(NotFoundError):
        await rs.get_referral_summary(session, uuid.uuid4())
