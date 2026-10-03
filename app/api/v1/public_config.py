"""Unauthenticated config the SPA needs at runtime (public OAuth client id)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/public", tags=["public"])


class PublicOAuthConfig(BaseModel):
    google_client_id: str


@router.get("/oauth-config", response_model=PublicOAuthConfig)
async def oauth_config() -> PublicOAuthConfig:
    settings = get_settings()
    return PublicOAuthConfig(
        google_client_id=(settings.google_oauth_client_id or "").strip()
    )
