"""Referral API endpoint (Task 17.1, Req 19).

Implements the referral surface from design.md ("Billing, Partner, Referral"):

    GET /referrals -> {code, count, rewards[]}

Returns the authenticated user's shareable referral code, their confirmed
referral count, and any granted referral rewards (Req 19.1, 19.2). Referral
recording itself happens at signup time in the auth register flow; this read
endpoint surfaces the resulting state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.deps import get_principal
from app.core.security.principal import Principal
from app.db.session import get_session
from app.services import referral_service

router = APIRouter(prefix="/referrals", tags=["referrals"])


class ReferralRewardOut(BaseModel):
    devices_granted: int
    months_granted: int
    granted_at: str | None = None
    expires_at: str | None = None


class ReferralSummaryResponse(BaseModel):
    code: str
    count: int
    rewards: list[ReferralRewardOut]


@router.get("", response_model=ReferralSummaryResponse)
async def get_referrals(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> ReferralSummaryResponse:
    """Return the caller's referral code, count, and rewards (Req 19.1, 19.2)."""
    summary = await referral_service.get_referral_summary(session, principal.user_id)
    # Persist a referral code generated lazily on first read.
    await session.commit()
    return ReferralSummaryResponse(**summary)
