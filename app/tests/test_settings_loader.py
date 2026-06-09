"""Unit tests for the platform settings read-through loader (Req 29.4).

Verifies the loader returns defaults, reflects writes immediately (the
platform-wide apply contract), and degrades gracefully when Redis is absent.
The source of truth is the in-memory placeholder store; the Redis cache is
optional in the test environment.
"""

from __future__ import annotations

import asyncio

from app.core.settings_loader import (
    _DEFAULT_SETTINGS,
    get_all_settings,
    get_setting,
    set_setting,
)


def test_returns_builtin_default_for_known_key() -> None:
    value = asyncio.run(get_setting("commission_default"))
    assert value == _DEFAULT_SETTINGS["commission_default"]


def test_unknown_key_returns_provided_default() -> None:
    value = asyncio.run(get_setting("does_not_exist", default="fallback"))
    assert value == "fallback"


def test_set_setting_applies_immediately() -> None:
    async def scenario() -> object:
        await set_setting("twofa_required", True)
        return await get_setting("twofa_required")

    assert asyncio.run(scenario()) is True


def test_get_all_settings_includes_defaults() -> None:
    settings = asyncio.run(get_all_settings())
    assert "pricing_tiers_monthly" in settings
    assert "plan_limits" in settings
