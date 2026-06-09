"""Unit tests for password hashing/verification (Task 2.1, Req 1.7, 1.9)."""

import pytest

from app.core.security import password as pw


def test_hash_password_produces_salted_argon2_hash():
    encoded = pw.hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2")
    # Hash must not contain the plaintext (one-way, Req 1.7).
    assert "correct horse battery staple" not in encoded


def test_hash_password_is_salted_unique_per_call():
    # Same password hashed twice yields different encoded hashes (random salt).
    assert pw.hash_password("same-password") != pw.hash_password("same-password")


def test_hash_password_rejects_empty():
    with pytest.raises(ValueError):
        pw.hash_password("")


def test_verify_correct_password_succeeds():
    stored = pw.hash_password("s3cret!")
    assert pw.verify_password("s3cret!", stored) is True
    assert pw.needs_reset(pw.CURRENT_FORMAT, stored) is False


def test_verify_wrong_password_fails():
    stored = pw.hash_password("s3cret!")
    assert pw.verify_password("wrong", stored) is False


def test_verify_empty_password_fails():
    stored = pw.hash_password("s3cret!")
    assert pw.verify_password("", stored) is False


def test_verify_missing_hash_fails():
    assert pw.verify_password("anything", None) is False


def test_verify_rejects_non_argon2_stored_value():
    # A plaintext/legacy stored value must never authenticate.
    assert pw.verify_password("hunter2", "hunter2") is False


def test_needs_reset_for_legacy_format():
    stored = pw.hash_password("s3cret!")
    # Valid argon2 hash but an unsupported format tag -> force reset (Req 1.9).
    assert pw.needs_reset("md5", stored) is True
    assert pw.needs_reset("bcrypt", stored) is True


def test_needs_reset_for_missing_hash():
    # No usable credential -> reset required before password auth.
    assert pw.needs_reset("argon2", None) is True
    assert pw.needs_reset("argon2", "") is True


def test_needs_reset_for_plaintext_value():
    # Format claims argon2 but the stored value is not a well-formed hash.
    assert pw.needs_reset("argon2", "plaintext-password") is True


def test_needs_reset_false_for_valid_credential():
    stored = pw.hash_password("s3cret!")
    assert pw.needs_reset(pw.CURRENT_FORMAT, stored) is False


def test_corrupt_argon2_hash_does_not_authenticate():
    # Prefix matches but the value is malformed: verify must fail, reset implied.
    corrupt = "$argon2id$not-a-real-hash"
    assert pw.verify_password("s3cret!", corrupt) is False


def test_needs_rehash_false_for_fresh_hash():
    stored = pw.hash_password("s3cret!")
    assert pw.needs_rehash(stored) is False
