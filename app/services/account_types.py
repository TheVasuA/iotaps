"""Self-service account kinds (Individual, Student, Company org)."""

from __future__ import annotations

ACCOUNT_INDIVIDUAL = "individual"
ACCOUNT_STUDENT = "student"
ACCOUNT_COMPANY = "company"

VALID_ACCOUNT_TYPES = frozenset(
    {ACCOUNT_INDIVIDUAL, ACCOUNT_STUDENT, ACCOUNT_COMPANY}
)

# Legacy org.type values still treated as company-style multi-tenant project centers.
LEGACY_COMPANY_TYPES = frozenset({"project_center", "platform"})


def normalize_account_type(value: str | None) -> str:
    if not value:
        return ACCOUNT_INDIVIDUAL
    v = value.strip().lower()
    if v in VALID_ACCOUNT_TYPES:
        return v
    if v in LEGACY_COMPANY_TYPES:
        return ACCOUNT_COMPANY
    return ACCOUNT_INDIVIDUAL


def is_multi_user_org(account_type: str | None) -> bool:
    return normalize_account_type(account_type) == ACCOUNT_COMPANY


def default_org_name(account_type: str, email: str, organization_name: str | None) -> str:
    if organization_name and organization_name.strip():
        return organization_name.strip()
    if account_type == ACCOUNT_COMPANY:
        return "My organization"
    local = email.split("@", 1)[0]
    if account_type == ACCOUNT_STUDENT:
        return f"{local}'s student workspace"
    return f"{local}'s workspace"
