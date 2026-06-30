"""Property-based test for the 14-day refund eligibility window (Task 15.3).

Uses Hypothesis to exercise the pure
:func:`app.services.subscription_service.within_refund_window` predicate across
a wide range of purchase / refund-request timestamps. No live Razorpay call is
made: this validates the eligibility boundary in isolation (Req 17.5, 17.7).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.subscription_service import (
    REFUND_WINDOW_DAYS,
    within_refund_window,
)

# Purchase timestamps anywhere in a broad, realistic range. Generate timezone
# -aware UTC datetimes (the production callers pass timestamptz / UTC values).
_paid_at = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

# Offset from purchase to the refund request, in seconds. Spans well before the
# purchase (negative) to long after the window, so examples land both inside and
# outside the 14-day boundary, including right on the edge.
_WINDOW_SECONDS = REFUND_WINDOW_DAYS * 24 * 60 * 60
_offset_seconds = st.integers(
    min_value=-3 * _WINDOW_SECONDS,
    max_value=3 * _WINDOW_SECONDS,
)


# Feature: iotaps-platform, Property 11: Refund eligibility window
@given(paid_at=_paid_at, offset_seconds=_offset_seconds)
@settings(max_examples=10, deadline=None)
def test_refund_eligible_iff_within_window(paid_at: datetime, offset_seconds: int):
    """Validates: Requirements 17.5, 17.7.

    For any purchase time and refund-request time, a refund is eligible if and
    only if the request occurs within 14 days (inclusive) of purchase, and is
    rejected once the window has elapsed.
    """
    requested_at = paid_at + timedelta(seconds=offset_seconds)
    deadline = paid_at + timedelta(days=REFUND_WINDOW_DAYS)

    eligible = within_refund_window(paid_at, requested_at)

    # The predicate must agree exactly with the inclusive 14-day boundary.
    assert eligible == (requested_at <= deadline)


# Feature: iotaps-platform, Property 11: Refund eligibility window
@given(paid_at=_paid_at)
@settings(max_examples=10, deadline=None)
def test_refund_boundary_is_inclusive(paid_at: datetime):
    """Validates: Requirements 17.5, 17.7.

    A request exactly at the 14-day boundary is accepted, one tick past it is
    rejected, and a same-instant request is accepted.
    """
    on_boundary = paid_at + timedelta(days=REFUND_WINDOW_DAYS)
    just_after = on_boundary + timedelta(seconds=1)

    assert within_refund_window(paid_at, paid_at) is True
    assert within_refund_window(paid_at, on_boundary) is True
    assert within_refund_window(paid_at, just_after) is False


# Feature: iotaps-platform, Property 11: Refund eligibility window
@given(
    paid_at=st.datetimes(
        min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)
    ),
    offset_seconds=_offset_seconds,
)
@settings(max_examples=10, deadline=None)
def test_naive_timestamps_treated_as_utc(paid_at: datetime, offset_seconds: int):
    """Validates: Requirements 17.5, 17.7.

    Naive datetimes (no tzinfo) are treated as UTC, so the eligibility decision
    is independent of whether the timestamp carries tz information.
    """
    requested_at = paid_at + timedelta(seconds=offset_seconds)
    deadline = paid_at + timedelta(days=REFUND_WINDOW_DAYS)

    eligible = within_refund_window(paid_at, requested_at)

    assert eligible == (requested_at <= deadline)
