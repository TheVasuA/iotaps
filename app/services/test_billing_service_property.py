"""Property-based test for volume discount pricing (Task 14.4, Req 16).

# Feature: iotaps-platform, Property 10: Volume discount pricing correctness and monotonicity

Property 10 (design.md "Correctness Properties"):

    For any device count, the resolved monthly per-device price equals the tier
    rate (1-10 -> ₹99, 11-50 -> ₹79, 51-200 -> ₹69, 201+ -> ₹59), the price is
    non-increasing as device count grows, the tier boundaries (10/11, 50/51,
    200/201) are exact, and an annual purchase totals ₹948 per device.

Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7

The pricing functions in :mod:`app.services.billing_service` are pure (no
DB/Redis/Razorpay), so each Hypothesis example simply calls them directly.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import billing_service as bs

# Device counts span every tier, including the open-ended 201+ band, and stay
# comfortably above the boundaries so the monotonicity walk covers all tiers.
_device_count = st.integers(min_value=1, max_value=5000)


def _expected_monthly_rate(device_count: int) -> int:
    """Reference tier rate derived straight from the Req 16.2-16.5 bands."""
    if device_count <= 10:
        return 99
    if device_count <= 50:
        return 79
    if device_count <= 200:
        return 69
    return 59


@settings(max_examples=30, deadline=None)
@given(device_count=_device_count)
def test_volume_pricing_correctness_and_monotonicity(device_count: int) -> None:
    """Property 10: volume discount pricing correctness and monotonicity.

    Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7
    """
    rate = bs.unit_price_monthly(device_count)

    # (a) Correctness: the resolved monthly rate equals the tier rate for the
    #     band the device count falls in (Req 16.2-16.5).
    assert rate == _expected_monthly_rate(device_count)

    # (b) The advertised rate is one of the four published tier rates (Req 16.6).
    assert rate in (99, 79, 69, 59)

    # (c) Annual purchases always total ₹948 per device (Req 16.1, 16.7),
    #     independent of the volume tier.
    assert bs.unit_price(device_count, "yearly") == 948
    assert bs.total(device_count, "yearly") == device_count * 948

    # (d) Monthly total is the per-device rate times the count (Req 16.6).
    assert bs.total(device_count, "monthly") == device_count * rate

    # (e) Monotonicity: adding one more device never raises the per-device
    #     monthly price (non-increasing as device_count grows).
    assert bs.unit_price_monthly(device_count + 1) <= rate


@settings(max_examples=30, deadline=None)
@given(data=st.data())
def test_per_device_price_is_globally_non_increasing(data: st.DataObject) -> None:
    """A larger fleet never costs more per device than a smaller one.

    Validates: Requirements 16.2, 16.3, 16.4, 16.5, 16.6
    """
    smaller = data.draw(st.integers(min_value=1, max_value=5000))
    larger = data.draw(st.integers(min_value=smaller, max_value=5000))
    assert bs.unit_price_monthly(larger) <= bs.unit_price_monthly(smaller)


def test_tier_boundaries_are_exact() -> None:
    """The 10/11, 50/51, 200/201 boundaries each step to the next tier exactly.

    Validates: Requirement 16.6
    """
    assert bs.unit_price_monthly(10) == 99 and bs.unit_price_monthly(11) == 79
    assert bs.unit_price_monthly(50) == 79 and bs.unit_price_monthly(51) == 69
    assert bs.unit_price_monthly(200) == 69 and bs.unit_price_monthly(201) == 59
