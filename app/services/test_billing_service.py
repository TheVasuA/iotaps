"""Unit tests for the volume discount pricing engine (Task 14.3, Req 16).

Verifies the tier rates, exact band boundaries, the fixed annual price, total
calculation, quote/plans serialisation, and input validation. The pricing
functions are pure, so no DB/Redis/MQTT is involved.
"""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.services import billing_service as bs


@pytest.mark.parametrize(
    "device_count, expected",
    [
        (1, 99),
        (5, 99),
        (10, 99),  # upper edge of tier 1 (Req 16.2)
        (11, 79),  # lower edge of tier 2 (Req 16.3)
        (50, 79),  # upper edge of tier 2
        (51, 69),  # lower edge of tier 3 (Req 16.4)
        (200, 69),  # upper edge of tier 3
        (201, 59),  # lower edge of tier 4 (Req 16.5)
        (1000, 59),
    ],
)
def test_unit_price_monthly_tiers(device_count, expected):
    assert bs.unit_price_monthly(device_count) == expected


def test_unit_price_monthly_boundaries_are_exact():
    # 10/11, 50/51, 200/201 each step to the next-cheaper tier (Req 16.6).
    assert bs.unit_price_monthly(10) != bs.unit_price_monthly(11)
    assert bs.unit_price_monthly(50) != bs.unit_price_monthly(51)
    assert bs.unit_price_monthly(200) != bs.unit_price_monthly(201)


def test_yearly_unit_price_is_fixed_948():
    # Annual price is a flat ₹948/device regardless of count (Req 16.1, 16.7).
    for count in (1, 10, 11, 50, 51, 200, 201, 5000):
        assert bs.unit_price(count, "yearly") == 948


def test_total_monthly_multiplies_tier_rate():
    # 25 devices -> tier 2 (₹79); total = 25 * 79.
    assert bs.total(25, "monthly") == 25 * 79


def test_total_yearly_multiplies_fixed_price():
    assert bs.total(100, "yearly") == 100 * 948


def test_quote_shape_monthly():
    q = bs.quote(11, "monthly")
    assert q == {
        "device_count": 11,
        "billing_cycle": "monthly",
        "unit_price": 79,
        "total": 11 * 79,
    }


def test_quote_shape_yearly():
    q = bs.quote(3, "yearly")
    assert q == {
        "device_count": 3,
        "billing_cycle": "yearly",
        "unit_price": 948,
        "total": 3 * 948,
    }


def test_cycle_normalization_is_case_insensitive():
    assert bs.normalize_cycle("MONTHLY") == "monthly"
    assert bs.normalize_cycle("  Yearly ") == "yearly"


def test_invalid_cycle_rejected():
    with pytest.raises(ValidationError):
        bs.unit_price(5, "weekly")


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_non_positive_device_count_rejected(bad):
    with pytest.raises(ValidationError):
        bs.unit_price_monthly(bad)


def test_boolean_device_count_rejected():
    # bool is a subclass of int; pricing must not silently accept True/False.
    with pytest.raises(ValidationError):
        bs.unit_price_monthly(True)


def test_plans_advertises_tiers_and_limits():
    p = bs.plans()
    assert p["free"]["max_devices"] == 2
    assert p["pro"]["max_devices"] is None
    assert p["pro"]["annual_unit_price"] == 948
    tiers = p["pricing_tiers"]
    assert [t["unit_price_monthly"] for t in tiers] == [99, 79, 69, 59]
    assert tiers[0]["min_devices"] == 1 and tiers[0]["max_devices"] == 10
    assert tiers[-1]["max_devices"] is None
