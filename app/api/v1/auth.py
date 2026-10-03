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
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator
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
from app.services.account_types import ACCOUNT_COMPANY, ACCOUNT_INDIVIDUAL, normalize_account_type
from app.services.signup_service import create_signup_organization, finalize_new_org

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
    account_type: str = Field(default=ACCOUNT_INDIVIDUAL)
    organization_name: str | None = Field(default=None, max_length=120)

    @field_validator("account_type")
    @classmethod
    def _norm_account_type(cls, v: str) -> str:
        return normalize_account_type(v)


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    org_id: str
    twofa_enabled: bool
    account_type: str = ACCOUNT_INDIVIDUAL
    organization_name: str = ""
    is_org_owner: bool = False


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
    account_type: str | None = None
    organization_name: str | None = Field(default=None, max_length=120)
    otp: str | None = None


class GoogleLinkRequest(BaseModel):
    id_token: str


class GoogleUnlinkRequest(BaseModel):
    password: str = ""


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class TwoFAEnableResponse(BaseModel):
    secret: str
    qr: str


class TwoFAVerifyRequest(BaseModel):
    otp: str


class TwoFAVerifyResponse(BaseModel):
    backup_codes: list[str] = Field(default_factory=list)


class TwoFAStatusResponse(BaseModel):
    enabled: bool
    backup_codes_remaining: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    theme_mode: Literal["light", "dark"] | None = None


class ProfileOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    org_id: str
    organization_name: str
    account_type: str
    twofa_enabled: bool
    backup_codes_remaining: int
    theme_mode: str
    oauth_provider: str | None
    is_org_owner: bool
    has_password: bool = True


class Disable2FARequest(BaseModel):
    password: str
    otp: str


class RegenerateBackupCodesRequest(BaseModel):
    password: str
    otp: str


class RegenerateBackupCodesResponse(BaseModel):
    backup_codes: list[str]


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


async def _org_for_user(session: AsyncSession, user: User) -> Organization | None:
    return await session.get(Organization, user.org_id)


def _user_out(user: User, org: Organization | None = None) -> UserOut:
    account_type = normalize_account_type(org.type if org else None)
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        org_id=str(user.org_id),
        twofa_enabled=bool(user.twofa_enabled),
        account_type=account_type,
        organization_name=org.name if org else "",
        is_org_owner=bool(user.is_org_owner),
    )


def _profile_out(user: User, org: Organization | None) -> ProfileOut:
    from app.services import twofa_backup

    account_type = normalize_account_type(org.type if org else None)
    return ProfileOut(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        org_id=str(user.org_id),
        organization_name=org.name if org else "",
        account_type=account_type,
        twofa_enabled=bool(user.twofa_enabled),
        backup_codes_remaining=twofa_backup.backup_codes_remaining(user),
        theme_mode=user.theme_mode or "light",
        oauth_provider=user.oauth_provider,
        is_org_owner=bool(user.is_org_owner),
        has_password=bool(user.password_hash),
    )


async def _verify_user_twofa(session: AsyncSession, user: User, otp: str | None) -> None:
    """Gate token issue when 2FA is enabled (password or Google sign-in)."""
    if not user.twofa_enabled:
        return
    if not otp:
        raise AuthenticationError(
            "Two-factor authentication code required",
            error_code="twofa_required",
        )
    from app.services import twofa_backup

    otp_ok = totp_service.verify_code(user.twofa_secret, otp)
    backup_ok = False
    if not otp_ok and otp:
        backup_ok = twofa_backup.verify_and_consume_backup_code(user, otp)
        if backup_ok:
            await session.commit()
    if not otp_ok and not backup_ok:
        raise AuthenticationError(
            "Invalid two-factor authentication code",
            error_code="twofa_invalid",
        )


def _apply_google_link(user: User, gmail_identity: str) -> None:
    user.gmail_identity = gmail_identity
    user.oauth_provider = "google"


async def _issue_token_pair(user: User, session: AsyncSession) -> TokenPair:
    redis = get_redis()
    settings = get_settings()
    org = await _org_for_user(session, user)
    account_type = normalize_account_type(org.type if org else None)
    org_name = org.name if org else ""
    access = jwt_service.create_access_token(
        user_id=str(user.id),
        org_id=str(user.org_id),
        role=user.role,
        email=user.email,
        account_type=account_type,
        org_name=org_name,
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

    org = await create_signup_organization(
        session,
        account_type=payload.account_type,
        email=str(payload.email),
        organization_name=payload.organization_name,
    )
    user = User(
        org_id=org.id,
        email=payload.email,
        gmail_identity=payload.email,
        password_hash=password_service.hash_password(payload.password),
        password_format=password_service.CURRENT_FORMAT,
        role="project_center",
        is_org_owner=True,
        twofa_enabled=False,
    )
    session.add(user)
    await session.flush()

    await finalize_new_org(session, org, user)

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
    logger.info(
        "user_registered",
        extra={"user_id": str(user.id), "account_type": org.type},
    )
    return RegisterResponse(user=_user_out(user, org))


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

    await _verify_user_twofa(session, user, payload.otp)

    from app.core.superadmin import ensure_superadmin_role

    await ensure_superadmin_role(session, user)

    return await _issue_token_pair(user, session)


@router.post("/oauth/google", response_model=TokenPair)
async def oauth_google(
    payload: GoogleOAuthRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Sign in/up via Google OAuth, issuing tokens on success (Req 1.2)."""
    email, gmail_identity = _verify_google_id_token(payload.id_token)

    from app.core.superadmin import ensure_superadmin_role, is_configured_superadmin_email

    user = await _get_user_by_email(session, email)
    if user is None:
        account_type = normalize_account_type(payload.account_type or ACCOUNT_INDIVIDUAL)
        org = await create_signup_organization(
            session,
            account_type=account_type,
            email=email,
            organization_name=payload.organization_name,
        )
        user = User(
            org_id=org.id,
            email=email,
            gmail_identity=gmail_identity,
            password_hash=None,
            role="super_admin" if is_configured_superadmin_email(email) else "project_center",
            is_org_owner=True,
            oauth_provider="google",
            twofa_enabled=False,
        )
        session.add(user)
        await session.flush()
        await finalize_new_org(session, org, user)
        await session.commit()
        await session.refresh(user)
        logger.info(
            "user_registered_oauth",
            extra={"user_id": str(user.id), "account_type": account_type},
        )

    # Deny new sign-ins for a suspended organization; existing sessions continue
    # until their tokens expire (Req 23.3).
    else:
        if await admin_service.organization_is_suspended(session, user.org_id):
            raise AuthenticationError(
                "Your organization is suspended; please contact your administrator",
                error_code="organization_suspended",
            )
        token_email = email.strip().lower()
        if user.email.strip().lower() != token_email:
            raise AuthenticationError(
                "Google account email does not match this user",
                error_code="oauth_email_mismatch",
            )
        await _verify_user_twofa(session, user, payload.otp)
        _apply_google_link(user, gmail_identity)
        await session.commit()
        await session.refresh(user)

    await ensure_superadmin_role(session, user)

    return await _issue_token_pair(user, session)


@router.post("/oauth/google/link", response_model=ProfileOut)
async def oauth_google_link(
    payload: GoogleLinkRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    """Link Google sign-in to the current account (emails must match)."""
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    email, gmail_identity = _verify_google_id_token(payload.id_token)
    if user.email.strip().lower() != email.strip().lower():
        raise ValidationError(
            "Use the Google account that matches your IoTAPS email",
            error_code="oauth_email_mismatch",
        )
    existing = await session.execute(
        select(User).where(User.gmail_identity == gmail_identity, User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationError(
            "This Google account is already linked to another user",
            error_code="google_identity_taken",
        )
    _apply_google_link(user, gmail_identity)
    await session.commit()
    await session.refresh(user)
    org = await _org_for_user(session, user)
    return _profile_out(user, org)


@router.post("/oauth/google/unlink", response_model=ProfileOut)
async def oauth_google_unlink(
    payload: GoogleUnlinkRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    """Remove Google sign-in; requires a password on the account."""
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if user.oauth_provider != "google":
        raise ValidationError("Google sign-in is not linked", error_code="oauth_not_linked")
    if not user.password_hash:
        raise ValidationError(
            "Set a password before unlinking Google sign-in",
            error_code="password_required",
        )
    if not password_service.verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Password is incorrect", error_code="invalid_password")
    user.oauth_provider = None
    await session.commit()
    await session.refresh(user)
    org = await _org_for_user(session, user)
    return _profile_out(user, org)


@router.post("/password/set", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def password_set(
    payload: SetPasswordRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Set an initial password (Google-only accounts)."""
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if user.password_hash:
        raise ValidationError(
            "Use change password instead",
            error_code="password_already_set",
        )
    user.password_hash = password_service.hash_password(payload.new_password)
    user.password_format = password_service.CURRENT_FORMAT
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    client_id = (getattr(settings, "google_oauth_client_id", None) or "").strip()
    if not client_id:
        raise AuthenticationError(
            "Google OAuth is not configured on the server",
            error_code="oauth_not_configured",
        )
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
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> AccessTokenResponse:
    """Rotate a refresh token and mint a new access token (Req 1.4, 1.5)."""
    from app.core.superadmin import ensure_superadmin_role

    redis = get_redis()
    settings = get_settings()
    try:
        refresh_claims = jwt_service.decode_refresh_token(payload.refresh_token, settings=settings)
    except jwt_service.TokenError as exc:
        raise AuthenticationError(
            "Refresh token is invalid or expired; please sign in again",
            error_code="refresh_invalid",
        ) from exc

    user_id = refresh_claims.sub
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError(
            "Refresh token is invalid or expired; please sign in again",
            error_code="refresh_invalid",
        )

    await ensure_superadmin_role(session, user)
    org = await _org_for_user(session, user)
    account_type = normalize_account_type(org.type if org else None)
    org_name = org.name if org else ""

    try:
        access, new_refresh = await jwt_service.rotate_refresh_token(
            redis,
            payload.refresh_token,
            settings=settings,
            role=user.role,
            org_id=str(user.org_id),
            email=user.email,
            account_type=account_type,
            org_name=org_name,
        )
    except jwt_service.TokenError as exc:
        raise AuthenticationError(
            "Refresh token is invalid or expired; please sign in again",
            error_code="refresh_invalid",
        ) from exc
    return AccessTokenResponse(access_token=access, refresh_token=new_refresh)


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


@router.post("/2fa/verify", response_model=TwoFAVerifyResponse)
async def twofa_verify(
    payload: TwoFAVerifyRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> TwoFAVerifyResponse:
    """Confirm a TOTP code and enable 2FA for the account (Req 1.8)."""
    from app.services import twofa_backup

    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if not totp_service.verify_code(user.twofa_secret, payload.otp):
        raise ValidationError("Invalid verification code", error_code="twofa_invalid")
    user.twofa_enabled = True
    codes = twofa_backup.issue_new_backup_codes(user)
    await session.commit()
    return TwoFAVerifyResponse(backup_codes=codes)


@router.get("/2fa/status", response_model=TwoFAStatusResponse)
async def twofa_status(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> TwoFAStatusResponse:
    from app.services import twofa_backup

    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    return TwoFAStatusResponse(
        enabled=bool(user.twofa_enabled),
        backup_codes_remaining=twofa_backup.backup_codes_remaining(user),
    )


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def twofa_disable(
    payload: Disable2FARequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    from app.services import twofa_backup

    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if user.password_hash:
        if not password_service.verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid password", error_code="invalid_password")
    if not user.twofa_enabled:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not totp_service.verify_code(user.twofa_secret, payload.otp):
        if not twofa_backup.verify_and_consume_backup_code(user, payload.otp):
            raise ValidationError("Invalid verification code", error_code="twofa_invalid")
    user.twofa_enabled = False
    user.twofa_secret = None
    user.twofa_backup_hashes = None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/2fa/backup-codes/regenerate", response_model=RegenerateBackupCodesResponse)
async def twofa_regenerate_backup_codes(
    payload: RegenerateBackupCodesRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> RegenerateBackupCodesResponse:
    from app.services import twofa_backup

    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if not user.twofa_enabled:
        raise ValidationError("Two-factor authentication is not enabled", error_code="twofa_off")
    if user.password_hash and not password_service.verify_password(
        payload.password, user.password_hash
    ):
        raise AuthenticationError("Invalid password", error_code="invalid_password")
    if not totp_service.verify_code(user.twofa_secret, payload.otp):
        raise ValidationError("Invalid verification code", error_code="twofa_invalid")
    codes = twofa_backup.issue_new_backup_codes(user)
    await session.commit()
    return RegenerateBackupCodesResponse(backup_codes=codes)


@router.get("/me", response_model=ProfileOut)
async def get_me(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    org = await _org_for_user(session, user)
    return _profile_out(user, org)


@router.patch("/me", response_model=ProfileOut)
async def update_me(
    payload: UpdateProfileRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ProfileOut:
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if payload.display_name is not None:
        name = payload.display_name.strip()
        user.display_name = name or None
    if payload.theme_mode is not None:
        user.theme_mode = payload.theme_mode
    await session.commit()
    await session.refresh(user)
    org = await _org_for_user(session, user)
    return _profile_out(user, org)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def password_change(
    payload: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    principal = _principal_from_header(authorization)
    user = await session.get(User, uuid.UUID(principal.sub))
    if user is None:
        raise NotFoundError("User not found")
    if not user.password_hash:
        raise ValidationError(
            "Password sign-in is not available for this account",
            error_code="oauth_only",
        )
    if not password_service.verify_password(payload.current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect", error_code="invalid_password")
    user.password_hash = password_service.hash_password(payload.new_password)
    user.password_format = password_service.CURRENT_FORMAT
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
