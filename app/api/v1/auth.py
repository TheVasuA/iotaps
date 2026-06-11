"""Auth_Service HTTP endpoints (Req 1).

Implements the auth surface from design.md ("Auth" API block):

    POST /auth/register                 -> create account
    POST /auth/login                    -> password (+ 2FA gate) -> tokens
    POST /auth/oauth/google             -> Google OAuth -> tokens
    POST /auth/refresh                  -> rotate refresh -> new access token
    POST /auth/logout                   -> revoke refresh token
    POST /auth/2fa/enable               -> provision TOTP secret + QR uri
    POST /auth/2fa/verify               -> confirm + enable 2FA
    POST /auth/password/reset-request   -> issue reset token (Req 23.4 reuse)
    POST /auth/password/reset           -> set new password via reset token

Token mechanics live in ``app.core.security.jwt``; password hashing in
``app.core.security.password``; TOTP in ``app.core.security.totp``. Tenant
filtering/RBAC middleware (task 2.5) is layered separately; these endpoints are
intentionally unauthenticated except 2FA-enable which derives the principal
from the bearer access token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.security import jwt as jwt_service
from app.core.security import password as password_service
from app.core.security import totp as totp_service
from app.db.session import get_session
from app.models.organization import Organization
from app.models.user import User
from app.services import referral_service
from app.services import admin_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Redis key for short-lived password-reset tokens (Req 1.9 reset path, 23.4).
_RESET_TOKEN_TTL_SECONDS = 3600


def _reset_token_key(token: str) -> str:
    return f"iotaps:pwreset:{token}"


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    referral_code: str | None = None


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    org_id: str
    twofa_enabled: bool


class RegisterResponse(BaseModel):
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    otp: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class GoogleOAuthRequest(BaseModel):
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class TwoFAEnableResponse(BaseModel):
    secret: str
    qr: str


class TwoFAVerifyRequest(BaseModel):
    otp: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=256)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_default_org(session: AsyncSession) -> Organization:
    """Resolve/create the organization a self-service signup belongs to.

    For the MVP a self-registering user becomes a Project_Center with their own
    Organization (tenant). Admin-driven onboarding (task 20.x) can assign users
    to existing orgs instead.
    """
    org = Organization(name="New Organization", type="project_center", plan="free")
    session.add(org)
    await session.flush()
    return org


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.org_id),
        twofa_enabled=bool(user.twofa_enabled),
    )


async def _issue_token_pair(user: User) -> TokenPair:
    redis = get_redis()
    settings = get_settings()
    access = jwt_service.create_access_token(
        user_id=str(user.id),
        org_id=str(user.org_id),
        role=user.role,
        email=user.email,
        settings=settings,
    )
    refresh = await jwt_service.issue_refresh_token(
        redis,
        user_id=str(user.id),
        org_id=str(user.org_id),
        role=user.role,
        settings=settings,
    )
    return TokenPair(access_token=access, refresh_token=refresh)


def _principal_from_header(authorization: str | None) -> jwt_service.AccessClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return jwt_service.decode_access_token(token)
    except jwt_service.TokenError as exc:
        raise AuthenticationError("Invalid or expired token") from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    """Create a new account with a salted password hash (Req 1.7)."""
    existing = await _get_user_by_email(session, payload.email)
    if existing is not None:
        raise ValidationError("An account with this email already exists", error_code="email_taken")

    org = await _get_default_org(session)
    user = User(
        org_id=org.id,
        email=payload.email,
        gmail_identity=payload.email,
        password_hash=password_service.hash_password(payload.password),
        password_format=password_service.CURRENT_FORMAT,
        role="project_center",
        twofa_enabled=False,
    )
    session.add(user)
    await session.flush()

    # Ensure the new org has a shareable referral code from signup (Req 19.1).
    await referral_service.ensure_referral_code(session, org)

    # Record the referral when a valid code is supplied (Req 19.1). A
    # self-service signup is its own org's founding user, so its org gets a
    # referral code generated lazily for sharing.
    if payload.referral_code:
        await referral_service.record_referral(
            session,
            referral_code=payload.referral_code,
            referred_user=user,
            referred_gmail=payload.email,
        )

    await session.commit()
    await session.refresh(user)
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return RegisterResponse(user=_user_out(user))


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Authenticate with email+password, gating on 2FA when enabled (Req 1.1, 1.3, 1.8)."""
    user = await _get_user_by_email(session, payload.email)
    # Generic error to avoid leaking which accounts exist (Req 1.3).
    if user is None:
        raise AuthenticationError("Invalid email or password")

    # Force reset path for legacy/invalid stored formats (Req 1.9).
    if password_service.needs_reset(user.password_format, user.password_hash):
        raise AuthenticationError(
            "Password reset required before sign-in",
            error_code="password_reset_required",
        )

    if not password_service.verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Invalid email or password")

    # Deny new sign-ins for a suspended organization; existing sessions keep
    # working until their tokens expire (Req 23.3).
    if await admin_service.organization_is_suspended(session, user.org_id):
        raise AuthenticationError(
            "Your organization is suspended; please contact your administrator",
            error_code="organization_suspended",
        )

    # 2FA gate: require a valid OTP before issuing tokens (Req 1.8).
    if user.twofa_enabled:
        if not payload.otp:
            raise AuthenticationError(
                "Two-factor authentication code required",
                error_code="twofa_required",
            )
        if not totp_service.verify_code(user.twofa_secret, payload.otp):
            raise AuthenticationError(
                "Invalid two-factor authentication code",
                error_code="twofa_invalid",
            )

    return await _issue_token_pair(user)


@router.post("/oauth/google", response_model=TokenPair)
async def oauth_google(
    payload: GoogleOAuthRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Sign in/up via Google OAuth, issuing tokens on success (Req 1.2)."""
    email, gmail_identity = _verify_google_id_token(payload.id_token)

    user = await _get_user_by_email(session, email)
    if user is None:
        org = await _get_default_org(session)
        user = User(
            org_id=org.id,
            email=email,
            gmail_identity=gmail_identity,
            password_hash=None,
            role="project_center",
            oauth_provider="google",
            twofa_enabled=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("user_registered_oauth", extra={"user_id": str(user.id)})

    # Deny new sign-ins for a suspended organization; existing sessions continue
    # until their tokens expire (Req 23.3).
    elif await admin_service.organization_is_suspended(session, user.org_id):
        raise AuthenticationError(
            "Your organization is suspended; please contact your administrator",
            error_code="organization_suspended",
        )

    return await _issue_token_pair(user)


def _verify_google_id_token(id_token_str: str) -> tuple[str, str]:
    """Verify a Google ID token and return (email, gmail_identity).

    Uses ``google-auth`` when a client id is configured; otherwise raises an
    auth error. Network/verification failures surface as authentication errors
    (Req 1.3 semantics for OAuth).
    """
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except Exception as exc:  # pragma: no cover - dependency missing
        raise AuthenticationError("Google OAuth is not available") from exc

    settings = get_settings()
    client_id = getattr(settings, "google_oauth_client_id", None)
    try:
        request = google_requests.Request()
        claims = google_id_token.verify_oauth2_token(
            id_token_str, request, client_id
        )
    except Exception as exc:
        raise AuthenticationError("Invalid Google credential") from exc

    email = claims.get("email")
    if not email or not claims.get("email_verified", False):
        raise AuthenticationError("Google account email not verified")
    return email, email


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest) -> AccessTokenResponse:
    """Rotate a refresh token and mint a new access token (Req 1.4, 1.5)."""
    redis = get_redis()
    try:
        access, _new_refresh = await jwt_service.rotate_refresh_token(
            redis, payload.refresh_token
        )
    except jwt_service.TokenError as exc:
        # Expired/revoked refresh tokens require re-authentication (Req 1.5).
        raise AuthenticationError(
            "Refresh token is invalid or expired; please sign in again",
            error_code="refresh_invalid",
        ) from exc
    return AccessTokenResponse(access_token=access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(payload: LogoutRequest) -> Response:
    """Revoke the presented refresh token (Req 1.6). Idempotent."""
    redis = get_redis()
    await jwt_service.revoke_refresh_token(redis, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/2fa/enable", response_model=TwoFAEnableResponse)
async def twofa_enable(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> TwoFAEnableResponse:
    """Provision a TOTP secret for the authenticated user (Req 1.8 setup)."""
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")

    secret = totp_service.generate_secret()
    user.twofa_secret = secret
    # Not enabled until the user verifies a code via /2fa/verify.
    user.twofa_enabled = False
    await session.commit()

    qr = totp_service.provisioning_uri(secret, user.email)
    return TwoFAEnableResponse(secret=secret, qr=qr)


@router.post("/2fa/verify", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def twofa_verify(
    payload: TwoFAVerifyRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Confirm a TOTP code and enable 2FA for the account (Req 1.8)."""
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if not totp_service.verify_code(user.twofa_secret, payload.otp):
        raise ValidationError("Invalid verification code", error_code="twofa_invalid")
    user.twofa_enabled = True
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/reset-request", status_code=202)
async def password_reset_request(
    payload: PasswordResetRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Issue a one-time password-reset token (Req 1.9 recovery, 23.4).

    Always returns 202 regardless of whether the account exists, to avoid
    account enumeration. When the account exists a reset token is stored in
    Redis with a short TTL.
    """
    user = await _get_user_by_email(session, payload.email)
    if user is not None:
        token = uuid.uuid4().hex
        redis = get_redis()
        if redis is not None:
            await redis.set(
                _reset_token_key(token), str(user.id), ex=_RESET_TOKEN_TTL_SECONDS
            )
        # Delivery (email) handled by the Notification_Sender (task 19.1).
        logger.info("password_reset_requested", extra={"user_id": str(user.id)})
    return {"status": "accepted"}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def password_reset(
    payload: PasswordResetConfirm,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Set a new password using a valid reset token (Req 1.9)."""
    redis = get_redis()
    if redis is None:
        raise ValidationError("Reset is temporarily unavailable", error_code="reset_unavailable")
    user_id = await redis.get(_reset_token_key(payload.token))
    if not user_id:
        raise ValidationError("Reset token is invalid or expired", error_code="reset_invalid")

    user = await session.get(User, uuid.UUID(str(user_id)))
    if user is None:
        raise NotFoundError("User not found")

    user.password_hash = password_service.hash_password(payload.new_password)
    user.password_format = password_service.CURRENT_FORMAT
    await session.commit()

    # One-time use: invalidate the reset token after a successful reset.
    await redis.delete(_reset_token_key(payload.token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
