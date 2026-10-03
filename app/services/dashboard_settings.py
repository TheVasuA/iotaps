"""Normalize dashboard settings stored in the JSONB column."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models.device import Device

TIME_RANGES = frozenset({"1d", "1w", "1mo", "3mo", "1y", "all"})
ORG_SCOPES = frozenset({"all", "selected"})


def _access(existing: dict | None) -> dict:
    raw = (existing or {}).get("access") or {}
    viewers = [str(v) for v in raw.get("viewers") or [] if v]
    editors = [str(v) for v in raw.get("editors") or [] if v]
    return {"viewers": viewers, "editors": editors}


async def normalize_settings(
    session: AsyncSession,
    org_id: uuid.UUID,
    incoming: dict | None,
    existing: dict | None,
) -> dict:
    """Merge a settings patch and reject unknown devices or ranges.

    ``access`` is not editable through this path. Sharing uses the access API.
    """
    base = dict(existing or {})
    patch = dict(incoming or {})
    patch.pop("access", None)
    merged = {**base, **patch}
    merged["access"] = _access(base)

    time_range = merged.get("time_range") or "1w"
    if time_range not in TIME_RANGES:
        raise ValidationError(
            "Unsupported time range",
            error_code="invalid_time_range",
        )
    merged["time_range"] = time_range

    if "device_ids" in patch:
        raw_ids = patch["device_ids"]
        if raw_ids is None:
            merged["device_ids"] = None
            merged["org_scope"] = "all"
        else:
            if not isinstance(raw_ids, list):
                raise ValidationError(
                    "device_ids must be a list",
                    error_code="invalid_device_ids",
                )
            parsed: list[uuid.UUID] = []
            for item in raw_ids:
                try:
                    parsed.append(uuid.UUID(str(item)))
                except (ValueError, TypeError) as exc:
                    raise ValidationError(
                        "Invalid device id",
                        error_code="invalid_device_ids",
                    ) from exc
            unique = list(dict.fromkeys(parsed))
            if unique:
                found = await session.execute(
                    select(Device.id).where(
                        Device.org_id == org_id,
                        Device.id.in_(unique),
                    )
                )
                found_ids = {row[0] for row in found.all()}
                if len(found_ids) != len(unique):
                    raise ValidationError(
                        "One or more devices are not in this workspace",
                        error_code="invalid_device_ids",
                    )
            merged["device_ids"] = [str(item) for item in unique]
            merged["org_scope"] = "selected"
    else:
        scope = merged.get("org_scope") or "all"
        if scope not in ORG_SCOPES:
            raise ValidationError(
                "Unsupported data source scope",
                error_code="invalid_org_scope",
            )
        merged["org_scope"] = scope

    return merged
