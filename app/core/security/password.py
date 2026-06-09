"""One-way salted password hashing with format tracking (Req 1.7, 1.9).

The Auth_Service stores passwords using a one-way salted hash (Req 1.7). We use
Argon2id (via ``argon2-cffi``) as the default format. Each stored credential
also carries a ``password_format`` marker (see ``users.password_format``) so the
platform can detect legacy/invalid formats and force a password reset (Req 1.9).

Force-reset rule (Req 1.9): if an account's stored password is not in the
required salted hash format - a legacy/unknown format, a missing hash, or a
value that is not a well-formed Argon2 hash (e.g. plaintext or corruption) -
then authentication MUST be rejected for that account until the user completes a
password reset. ``needs_reset`` detects this condition; the Auth_Service (task
2.3) checks it before attempting ``verify_password``.

This module is owned by task 2.1 and exposes a stable interface that the
Auth_Service (task 2.3) depends on: ``hash_password`` / ``verify_password`` /
``needs_reset`` / ``needs_rehash`` / ``CURRENT_FORMAT``.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Current canonical password format identifier stored in ``users.password_format``.
CURRENT_FORMAT = "argon2"

# Formats we still know how to verify against. Anything outside this set is
# considered legacy/invalid and forces a reset (Req 1.9).
SUPPORTED_FORMATS = frozenset({"argon2"})

# Argon2 encoded hashes always begin with this marker (Argon2id variant).
_ARGON2_PREFIX = "$argon2"

# Shared hasher with library defaults (Argon2id, random per-hash salt). A single
# instance is safe to reuse and keeps parameters consistent across the app.
_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    """Return a one-way, salted argon2 hash of ``plaintext`` (Req 1.7).

    The returned hash is the canonical ``CURRENT_FORMAT`` ("argon2") format and
    embeds a random per-call salt, so hashing the same password twice yields
    different encoded strings.

    Raises:
        ValueError: if ``plaintext`` is not a non-empty string.
    """
    if not isinstance(plaintext, str) or plaintext == "":
        raise ValueError("password must be a non-empty string")
    return _hasher.hash(plaintext)


def _is_well_formed_argon2(password_hash: str | None) -> bool:
    """Return whether ``password_hash`` looks like an encoded Argon2 hash."""
    return isinstance(password_hash, str) and password_hash.startswith(_ARGON2_PREFIX)


def verify_password(plaintext: str, password_hash: str | None) -> bool:
    """Verify ``plaintext`` against a stored argon2 ``password_hash``.

    Returns ``False`` (never raises) for a mismatch, an empty/missing password,
    a missing hash, or a hash that is not in a recognised salted format. The
    Auth_Service should call :func:`needs_reset` first to enforce the
    force-reset rule (Req 1.9); this function additionally refuses to
    authenticate against anything that is not a well-formed Argon2 hash.
    """
    if not password_hash or not isinstance(plaintext, str) or plaintext == "":
        return False
    # Never treat a non-Argon2 (e.g. legacy/plaintext) stored value as valid.
    if not _is_well_formed_argon2(password_hash):
        return False
    try:
        return _hasher.verify(password_hash, plaintext)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def needs_reset(password_format: str | None, password_hash: str | None) -> bool:
    """Whether the account must complete a password reset before auth (Req 1.9).

    An account needs a reset when its stored password is not in the required
    salted hash format: there is no usable hash, the stored format is one we no
    longer support, or the stored value is not a well-formed Argon2 hash (e.g. a
    legacy plaintext value or corruption). Until the reset replaces the
    credential, password authentication for the account is rejected.
    """
    if not password_hash:
        return True
    if (password_format or "") not in SUPPORTED_FORMATS:
        return True
    # Format tag claims a supported algorithm but the stored value is not a
    # well-formed Argon2 hash -> treat as invalid and force a reset.
    return not _is_well_formed_argon2(password_hash)


def needs_rehash(password_hash: str) -> bool:
    """Whether the stored hash should be upgraded to current argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return True
