"""One-time 2FA backup codes (hashed at rest)."""

from __future__ import annotations

import json
import secrets
import string

from app.core.security import password as password_service

BACKUP_CODE_COUNT = 10
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def generate_plain_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    for _ in range(count):
        part = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        part2 = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        codes.append(f"{part}-{part2}")
    return codes


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [password_service.hash_password(_normalize_code(c)) for c in codes]


def store_hashes(user, hashes: list[str]) -> None:
    user.twofa_backup_hashes = hashes


def backup_codes_remaining(user) -> int:
    raw = user.twofa_backup_hashes
    if not raw:
        return 0
    if isinstance(raw, list):
        return len(raw)
    return 0


def verify_and_consume_backup_code(user, code: str) -> bool:
    raw = user.twofa_backup_hashes
    if not raw or not isinstance(raw, list):
        return False
    normalized = _normalize_code(code)
    if not normalized:
        return False
    remaining: list[str] = []
    consumed = False
    for stored_hash in raw:
        if not consumed and password_service.verify_password(normalized, stored_hash):
            consumed = True
            continue
        remaining.append(stored_hash)
    if consumed:
        user.twofa_backup_hashes = remaining
    return consumed


def issue_new_backup_codes(user) -> list[str]:
    plain = generate_plain_backup_codes()
    store_hashes(user, hash_backup_codes(plain))
    return plain
