"""Property-based tests for password hashing (Task 2.2, Req 1.7, 1.9).

Uses Hypothesis to exercise :mod:`app.core.security.password` across a wide
range of password strings, validating the round-trip / secrecy property of the
one-way salted hash.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.security import password as pw


# Passwords are non-empty strings. ``hash_password`` rejects the empty string,
# so we constrain the generator to the valid input space (min_size=1) and use a
# wide character set (incl. unicode, whitespace, symbols) to stress the hasher.
_passwords = st.text(min_size=1, max_size=128)


# Feature: iotaps-platform, Property 4: Password hash round-trip and secrecy
@given(password=_passwords, other=_passwords)
# Argon2id is intentionally slow (CPU/memory-hard), so each example takes well
# over Hypothesis' default 200ms deadline. Disable the per-example deadline; the
# cost is inherent to secure hashing, not a performance regression.
@settings(max_examples=30, deadline=None)
def test_password_hash_round_trip_and_secrecy(password: str, other: str):
    """Validates: Requirements 1.7, 1.9.

    For any password string:
      * verifying it against its stored salted hash succeeds,
      * verifying any *different* string fails, and
      * the stored value never equals the plaintext password.
    """
    stored = pw.hash_password(password)

    # Round-trip: the original password verifies against its stored hash.
    assert pw.verify_password(password, stored) is True

    # Secrecy: the stored value never equals the plaintext password.
    assert stored != password

    # A valid, freshly-created credential never needs a reset (Req 1.9).
    assert pw.needs_reset(pw.CURRENT_FORMAT, stored) is False

    # Any *different* string must fail verification.
    if other != password:
        assert pw.verify_password(other, stored) is False
