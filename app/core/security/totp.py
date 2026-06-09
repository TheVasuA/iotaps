"""Two-factor authentication (TOTP) helpers (Req 1.8).

WHERE two-factor authentication is enabled for an account, the Auth_Service must
require a second verification factor before issuing a JWT access token (Req 1.8).
This module wraps ``pyotp`` to generate per-user TOTP secrets, build provisioning
URIs for authenticator apps, and verify submitted one-time codes.

The TOTP secret is stored in ``users.twofa_secret`` and the enabled flag in
``users.twofa_enabled``.
"""

from __future__ import annotations

import pyotp

# Issuer label shown in authenticator apps.
TOTP_ISSUER = "IoTAPS"


def generate_secret() -> str:
    """Return a new base32 TOTP secret for a user."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str) -> str:
    """Build an ``otpauth://`` URI for QR provisioning in authenticator apps."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name, issuer_name=TOTP_ISSUER
    )


def verify_code(secret: str | None, code: str | None, *, valid_window: int = 1) -> bool:
    """Verify a submitted TOTP ``code`` against ``secret``.

    ``valid_window`` allows a small clock-skew tolerance (one step either side).
    Returns ``False`` (never raises) for missing inputs or a bad code.
    """
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=valid_window)
    except Exception:
        return False
