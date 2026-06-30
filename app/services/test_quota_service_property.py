"""Property-based test for Message_Quota counting + monthly reset (Task 14.2).

# Feature: iotaps-platform, Property 8: Message quota counts telemetry only and resets monthly

Property 8 (design.md "Correctness Properties"):

    For any stream of mixed messages, the Free_Plan monthly quota counter
    increases by exactly the number of telemetry messages and is unaffected by
    Command, Command_ACK, and Device status messages; and for any month
    boundary crossing, the counter resets to zero for the new month.

Validates: Requirements 15.3, 15.4, 15.6

Drives the real :func:`app.services.quota_service.count_telemetry_message`
against an in-memory ``fakeredis`` client (no live Redis/Postgres). Each
Hypothesis example generates a mixed sequence of messages - each tagged with a
message type (telemetry/command/ack/status) and a billing month - replays them
in order, then asserts that every month's counter equals exactly the number of
*telemetry* messages assigned to that month and nothing else.

Months are expressed as non-negative offsets from the current UTC month so each
quota key's month-end ``expireat`` always lands in the future; otherwise
``fakeredis`` would expire the key the instant it is written and the per-month
counter could never be observed.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone

import fakeredis.aioredis
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core import redis_keys as rk
from app.core.mqtt_topics import MessageType
from app.services import quota_service as qs

# The four message types that can appear in the stream. Only TELEMETRY is ever
# counted toward the quota; COMMAND/ACK/STATUS must never increment it (15.4).
_MESSAGE_TYPES = [
    MessageType.TELEMETRY,
    MessageType.COMMAND,
    MessageType.ACK,
    MessageType.STATUS,
]

_FREE_PLAN = "free"


def _month_datetime(offset: int) -> datetime:
    """Return a UTC ``datetime`` ``offset`` whole months after the current month.

    The instant is the first day of that month at noon, so the month-end
    ``expireat`` set by the quota service is always strictly in the future for
    every non-negative offset and ``fakeredis`` keeps the key alive long enough
    to assert on it.
    """
    base = datetime.now(timezone.utc)
    total = (base.month - 1) + offset
    year = base.year + total // 12
    month = total % 12 + 1
    return datetime(year, month, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Generators: a mixed stream of (message_type, month_offset) messages.
# ---------------------------------------------------------------------------
_message = st.tuples(
    st.sampled_from(_MESSAGE_TYPES),
    st.integers(min_value=0, max_value=3),  # up to 4 distinct billing months
)

_stream = st.lists(_message, min_size=0, max_size=60)


async def _run(stream: list[tuple[MessageType, int]]) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    org_id = "org-prop-8"

    # Expected telemetry count per month offset, maintained independently of the
    # service so the assertion is a true oracle.
    expected_telemetry: Counter[int] = Counter()

    try:
        for message_type, offset in stream:
            now = _month_datetime(offset)
            result = await qs.count_telemetry_message(
                redis, org_id, _FREE_PLAN, message_type=message_type, now=now
            )

            if message_type is MessageType.TELEMETRY:
                expected_telemetry[offset] += 1
                # Telemetry on a metered (Free) plan is always counted, and the
                # returned running count equals this month's telemetry tally so
                # far (15.3).
                assert result.counted is True
                assert result.count == expected_telemetry[offset]
            else:
                # Command/ACK/status are excluded from the quota entirely (15.4):
                # they never count and never touch a counter.
                assert result.counted is False
                assert result.count == 0

        # Per-month invariant: each month's stored counter equals exactly the
        # number of telemetry messages for that month (15.3, 15.4), and months
        # are keyed independently so each starts fresh from its own telemetry
        # only - a new month is unaffected by prior months (15.6).
        offsets_seen = {offset for _, offset in stream}
        for offset in offsets_seen:
            key = rk.quota_key(org_id, _month_datetime(offset))
            stored = await redis.get(key)
            expected = expected_telemetry.get(offset, 0)
            if expected == 0:
                # No telemetry that month -> no counter was ever created.
                assert stored is None
            else:
                assert stored is not None
                assert int(stored) == expected

        # Global invariant: the sum across all month counters equals the total
        # telemetry in the stream - nothing else inflates the quota.
        total_telemetry = sum(expected_telemetry.values())
        total_stored = 0
        for offset in offsets_seen:
            stored = await redis.get(rk.quota_key(org_id, _month_datetime(offset)))
            if stored is not None:
                total_stored += int(stored)
        assert total_stored == total_telemetry
    finally:
        await redis.aclose()


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(stream=_stream)
def test_quota_counts_telemetry_only_and_resets_monthly(
    stream: list[tuple[MessageType, int]],
) -> None:
    """Property 8: message quota counts telemetry only and resets monthly.

    Validates: Requirements 15.3, 15.4, 15.6
    """
    asyncio.run(_run(stream))
