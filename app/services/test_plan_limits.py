"""Unit tests for plan limits (Task 14.1, Req 15.1, 15.2, 15.7)."""

from __future__ import annotations

import pytest

from app.services import plan_limits as pl


def test_free_plan_limits_match_requirement_15_1():
    limits = pl.limits_for_plan("free")
    assert limits.max_devices == 2
    assert limits.max_messages_per_month == 20000
    assert limits.retention_days == 7
    assert limits.max_sensors == 10
    assert limits.max_rules == 2
    assert limits.full_control is False


def test_pro_plan_limits_match_requirement_15_2():
    limits = pl.limits_for_plan("pro")
    assert limits.max_devices is None  # unlimited
    assert limits.max_messages_per_month is None  # unlimited
    assert limits.max_sensors == 20
    assert limits.max_rules is None  # unlimited
    assert limits.full_control is True


@pytest.mark.parametrize("plan", [None, "", "  ", "enterprise", "FREEMIUM"])
def test_ambiguous_plan_falls_back_to_free(plan):
    # Unrecognised plans must never grant Pro benefits (Req 15.7).
    assert pl.limits_for_plan(plan) == pl.FREE_LIMITS


@pytest.mark.parametrize("plan", ["pro", "Pro", " PRO "])
def test_pro_matching_is_case_and_whitespace_insensitive(plan):
    assert pl.limits_for_plan(plan) == pl.PRO_LIMITS


def test_is_metered():
    assert pl.is_metered("free") is True
    assert pl.is_metered("mystery") is True  # ambiguous -> metered (Req 15.7)
    assert pl.is_metered("pro") is False  # unlimited (Req 15.2)


def test_has_full_control():
    assert pl.has_full_control("pro") is True
    assert pl.has_full_control("free") is False
    assert pl.has_full_control(None) is False  # ambiguous -> view-only
