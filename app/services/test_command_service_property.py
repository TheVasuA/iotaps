"""Property-based test for the command status state machine (Task 9.2, Req 9.4-9.7).

# Feature: iotaps-platform, Property 15: Command status follows a valid state machine

Property 15 (design.md "Correctness Properties"):

    For any sequence of events applied to a command, the command's status only
    ever follows a legal transition of the command state machine. A command is
    born in SENT (issued while online) or QUEUED (issued while offline); from
    SENT an ACK moves it to CONFIRMED and an ACK timeout moves it to
    UNACKNOWLEDGED; from QUEUED a reconnect flush moves it to SENT; the terminal
    statuses CONFIRMED and UNACKNOWLEDGED never transition again; and any event
    that is not a legal transition from the current status is a no-op.

Validates: Requirements 9.4, 9.5, 9.6, 9.7

The transitions are driven through the *real* service handlers
(:func:`confirm_command`, :func:`expire_command`, :func:`flush_queued_commands`)
against an in-memory ``fakeredis`` store, so the property checks the behaviour
that actually ships, not a reimplementation. No live MQTT/Redis is used.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import fakeredis.aioredis
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core import redis_keys as rk
from app.services.command_service import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATUSES,
    CommandEvent,
    CommandRecord,
    CommandStatus,
    confirm_command,
    expire_command,
    flush_queued_commands,
    next_status,
)

_ORG_ID = "org-prop"
_DEVICE_ID = "dev-prop"

# The two ways a command can be born, then any mix of post-issue events. The
# issue events are also drawn into the follow-up stream to confirm re-issuing an
# existing command is a no-op (it is never a legal transition from a real state).
_initial_issue = st.sampled_from(
    [CommandEvent.ISSUE_ONLINE, CommandEvent.ISSUE_OFFLINE]
)
_follow_up_event = st.sampled_from(list(CommandEvent))
_event_sequence = st.lists(_follow_up_event, min_size=0, max_size=12)


def _record(command_id: str, status: CommandStatus) -> CommandRecord:
    return CommandRecord(
        command_id=command_id,
        device_id=_DEVICE_ID,
        org_id=_ORG_ID,
        type="on",
        value=None,
        status=status,
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )


async def _current_status(redis, command_id: str) -> CommandStatus:
    raw = await redis.get(rk.command_record_key(command_id))
    return CommandRecord.from_dict(json.loads(raw)).status


async def _apply_event(redis, command_id: str, event: CommandEvent) -> None:
    """Drive ``event`` through the real handler that owns it.

    Re-issue events (ISSUE_ONLINE/ISSUE_OFFLINE) for an already-existing command
    have no handler and are intentional no-ops. The ACK/timeout/flush handlers
    each consult :func:`next_status`, so an event that is not legal from the
    current status leaves the stored record untouched.
    """
    if event is CommandEvent.ACK:
        await confirm_command(redis, command_id)
    elif event is CommandEvent.TIMEOUT:
        await expire_command(redis, command_id)
    elif event is CommandEvent.RECONNECT_FLUSH:
        async def _publisher(topic: str, payload: str) -> None:
            return None

        # flush pops from the device queue; a QUEUED command was pushed at
        # issue time, so the flush can legally promote it QUEUED -> SENT.
        await flush_queued_commands(redis, _ORG_ID, _DEVICE_ID, _publisher)
    # ISSUE_* on an existing command: no handler, deliberate no-op.


async def _run(initial: CommandEvent, events: list[CommandEvent]) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        command_id = str(uuid.uuid4())

        # ---- Birth: issue online -> SENT, issue offline -> QUEUED (Req 9.5).
        initial_status = next_status(None, initial)
        assert initial_status in (CommandStatus.SENT, CommandStatus.QUEUED)
        record = _record(command_id, initial_status)
        await redis.set(
            rk.command_record_key(command_id), json.dumps(record.to_dict())
        )
        if initial_status is CommandStatus.QUEUED:
            # Mirror the offline-issue path so a later reconnect flush has a
            # queued entry to promote (Req 9.6).
            await redis.rpush(
                rk.command_queue_key(_DEVICE_ID),
                json.dumps({"command_id": command_id, "type": "on", "value": None}),
            )

        # ---- Apply each event and assert the status moves only along a legal
        #      transition (or stays put when the event is not legal).
        for event in events:
            before = await _current_status(redis, command_id)
            predicted = next_status(before, event)

            await _apply_event(redis, command_id, event)

            after = await _current_status(redis, command_id)

            if predicted is None:
                # Illegal / duplicate event is a strict no-op (Req 9.4, 9.7:
                # a late ACK after timeout or a second ACK never changes state).
                assert after is before, (
                    f"non-transition event {event.value} changed "
                    f"{before.value} -> {after.value}"
                )
            else:
                # A real change must be exactly the legal target, and the
                # (source, event) pair must be in the state machine.
                assert (before, event) in LEGAL_TRANSITIONS
                assert after is predicted, (
                    f"event {event.value} from {before.value} produced "
                    f"{after.value}, expected {predicted.value}"
                )

            # Terminal statuses are absorbing: once CONFIRMED/UNACKNOWLEDGED,
            # nothing downgrades or re-confirms them (Req 9.4, 9.7).
            if before in TERMINAL_STATUSES:
                assert after is before
    finally:
        await redis.aclose()


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(initial=_initial_issue, events=_event_sequence)
def test_command_status_follows_valid_state_machine(
    initial: CommandEvent, events: list[CommandEvent]
) -> None:
    """Property 15: command status follows a valid state machine.

    Validates: Requirements 9.4, 9.5, 9.6, 9.7
    """
    asyncio.run(_run(initial, events))
