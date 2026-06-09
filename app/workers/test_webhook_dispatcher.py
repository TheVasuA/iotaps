"""Unit tests for the Webhook_Dispatcher retry policy (Task 19.3, Req 20.3, 20.4).

These exercise the pure :class:`RetryPolicy` and the async ``deliver_webhook``
delivery path with an injected fake HTTP poster and a fake ``sleep_fn`` (no live
network, no real backoff waits). They verify the behaviour Req 20.4 mandates:

- a delivery is retried according to the configured policy, backing off with
  exponential growth capped at the policy maximum (the fake ``sleep_fn`` records
  the backoff schedule)
- a 2xx response stops retrying immediately (no further attempts, no backoff)
- after the maximum attempts are exhausted the delivery is marked failed and the
  injected ``on_failed`` callback fires exactly once (Req 20.4)
"""

from __future__ import annotations

import pytest

from app.workers import webhook_dispatcher as wd


# ---------------------------------------------------------------------------
# Fakes: a poster returning a scripted sequence of statuses, and a sleep that
# records the backoff schedule instead of actually waiting.
# ---------------------------------------------------------------------------
class _FakePoster:
    """Records each POST and returns the next scripted status (or raises)."""

    def __init__(self, results: list):
        # ``results`` entries are ints (status codes) or Exception instances.
        self._results = list(results)
        self.calls: list[tuple[str, dict, dict | None]] = []

    async def __call__(self, url, payload, headers=None) -> int:
        self.calls.append((url, payload, headers))
        outcome = self._results[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeSleep:
    """Records every delay it is asked to await (no real waiting)."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _event(retry_policy: dict | None = None, **kwargs) -> wd.WebhookEvent:
    return wd.WebhookEvent(
        url="https://example.test/hook",
        payload={"event": "alert", "value": 42},
        retry_policy=retry_policy,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# RetryPolicy backoff schedule (pure; Req 20.4)
# ---------------------------------------------------------------------------
def test_backoff_for_retry_grows_exponentially():
    """Backoff is initial * factor**i for each 0-based retry index."""
    policy = wd.RetryPolicy(
        max_attempts=5, backoff_initial=1.0, backoff_factor=2.0, backoff_max=60.0
    )
    assert policy.backoff_for_retry(0) == 1.0
    assert policy.backoff_for_retry(1) == 2.0
    assert policy.backoff_for_retry(2) == 4.0
    assert policy.backoff_for_retry(3) == 8.0


def test_backoff_for_retry_is_capped_at_max():
    """Backoff never exceeds the configured maximum, no matter the index."""
    policy = wd.RetryPolicy(
        max_attempts=10, backoff_initial=1.0, backoff_factor=2.0, backoff_max=5.0
    )
    assert policy.backoff_for_retry(2) == 4.0  # below cap
    assert policy.backoff_for_retry(3) == 5.0  # 8.0 -> capped
    assert policy.backoff_for_retry(20) == 5.0  # huge -> still capped


def test_backoff_for_negative_index_is_zero():
    """A negative retry index yields no wait."""
    policy = wd.RetryPolicy()
    assert policy.backoff_for_retry(-1) == 0.0


def test_from_config_uses_defaults_for_missing_or_invalid():
    """An absent/malformed policy falls back to the bounded defaults."""
    assert wd.RetryPolicy.from_config(None) == wd.RetryPolicy()
    assert wd.RetryPolicy.from_config("nope") == wd.RetryPolicy()
    assert wd.RetryPolicy.from_config({}).max_attempts == wd.DEFAULT_MAX_ATTEMPTS


def test_from_config_max_attempts_never_below_one():
    """At least one attempt is always made even for a zero/negative config."""
    assert wd.RetryPolicy.from_config({"max_attempts": 0}).max_attempts == 1
    assert wd.RetryPolicy.from_config({"max_attempts": -3}).max_attempts == 1


# ---------------------------------------------------------------------------
# deliver_webhook: retry follows the configured backoff schedule (Req 20.4)
# ---------------------------------------------------------------------------
async def test_retries_follow_configured_backoff_schedule():
    """Failures retry up to max_attempts, sleeping the exponential schedule."""
    poster = _FakePoster([500, 502, 503])  # all fail -> exhaust 3 attempts
    sleep = _FakeSleep()
    event = _event(
        {
            "max_attempts": 3,
            "backoff_initial": 1.0,
            "backoff_factor": 2.0,
            "backoff_max": 60.0,
        }
    )

    result = await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    # Three attempts were made against the configured URL.
    assert len(poster.calls) == 3
    assert result.attempts == 3
    # Backoff happens BETWEEN attempts only: 2 waits for 3 attempts, following
    # delay(0)=1.0 then delay(1)=2.0 (no wait after the final attempt).
    assert sleep.delays == [1.0, 2.0]
    assert result.delivered is False
    assert result.failed is True
    assert result.last_status == 503


async def test_backoff_schedule_is_capped_during_delivery():
    """The recorded backoff schedule honours the policy's max cap."""
    poster = _FakePoster([500, 500, 500, 500])  # 4 attempts, all fail
    sleep = _FakeSleep()
    event = _event(
        {
            "max_attempts": 4,
            "backoff_initial": 2.0,
            "backoff_factor": 3.0,
            "backoff_max": 10.0,
        }
    )

    await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    # delay(0)=2.0, delay(1)=6.0, delay(2)=18.0 -> capped to 10.0
    assert sleep.delays == [2.0, 6.0, 10.0]


async def test_transport_error_counts_as_failed_attempt_and_retries():
    """A raised transport error is treated like a non-2xx: it retries."""
    poster = _FakePoster([ConnectionError("boom"), 200])
    sleep = _FakeSleep()
    event = _event({"max_attempts": 3, "backoff_initial": 1.0, "backoff_factor": 2.0})

    result = await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    assert len(poster.calls) == 2  # errored once, then succeeded
    assert result.delivered is True
    assert result.attempts == 2
    assert sleep.delays == [1.0]  # one backoff between the two attempts


# ---------------------------------------------------------------------------
# deliver_webhook: a 2xx stops retrying immediately (Req 20.3)
# ---------------------------------------------------------------------------
async def test_success_stops_retrying_immediately():
    """A 2xx on the first attempt means no retries and no backoff."""
    poster = _FakePoster([200, 200, 200])
    sleep = _FakeSleep()
    event = _event({"max_attempts": 5, "backoff_initial": 1.0})

    result = await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    assert len(poster.calls) == 1  # stopped after the first success
    assert result.attempts == 1
    assert result.delivered is True
    assert result.failed is False
    assert result.last_status == 200
    assert sleep.delays == []  # never backed off


async def test_success_after_some_failures_stops_at_first_2xx():
    """Delivery stops at the first 2xx even after earlier failures."""
    poster = _FakePoster([500, 201, 500])  # 2nd attempt succeeds (201 is 2xx)
    sleep = _FakeSleep()
    event = _event({"max_attempts": 5, "backoff_initial": 1.0, "backoff_factor": 2.0})

    result = await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    assert len(poster.calls) == 2
    assert result.attempts == 2
    assert result.delivered is True
    assert result.last_status == 201
    assert sleep.delays == [1.0]  # one backoff before the successful retry


# ---------------------------------------------------------------------------
# deliver_webhook: final failure marking + on_failed callback (Req 20.4)
# ---------------------------------------------------------------------------
async def test_marks_failed_and_fires_on_failed_after_max_attempts():
    """After max attempts with no 2xx the delivery is failed and on_failed fires."""
    poster = _FakePoster([500, 500, 500])
    sleep = _FakeSleep()
    fired: list[tuple[wd.WebhookEvent, wd.DeliveryResult]] = []

    async def on_failed(ev, res) -> None:
        fired.append((ev, res))

    event = _event({"max_attempts": 3, "backoff_initial": 1.0, "backoff_factor": 2.0})

    result = await wd.deliver_webhook(
        event, poster, sleep_fn=sleep, on_failed=on_failed
    )

    assert result.failed is True
    assert result.delivered is False
    assert result.attempts == 3
    # on_failed fired exactly once with the same event + result.
    assert len(fired) == 1
    assert fired[0][0] is event
    assert fired[0][1] is result


async def test_on_failed_not_called_on_success():
    """on_failed must not fire when a delivery ultimately succeeds."""
    poster = _FakePoster([500, 200])
    sleep = _FakeSleep()
    fired: list = []

    async def on_failed(ev, res) -> None:
        fired.append((ev, res))

    event = _event({"max_attempts": 3, "backoff_initial": 1.0})

    result = await wd.deliver_webhook(
        event, poster, sleep_fn=sleep, on_failed=on_failed
    )

    assert result.delivered is True
    assert fired == []


async def test_on_failed_error_does_not_propagate():
    """A raising on_failed callback never crashes delivery (failure must be recorded)."""
    poster = _FakePoster([500])
    sleep = _FakeSleep()

    async def on_failed(ev, res) -> None:
        raise RuntimeError("could not persist failure")

    event = _event({"max_attempts": 1})

    # Should not raise despite the callback blowing up.
    result = await wd.deliver_webhook(
        event, poster, sleep_fn=sleep, on_failed=on_failed
    )
    assert result.failed is True
    assert result.attempts == 1


async def test_single_attempt_policy_makes_no_backoff():
    """A max_attempts=1 policy makes one attempt and never backs off."""
    poster = _FakePoster([500])
    sleep = _FakeSleep()
    event = _event({"max_attempts": 1})

    result = await wd.deliver_webhook(event, poster, sleep_fn=sleep)

    assert len(poster.calls) == 1
    assert result.attempts == 1
    assert result.failed is True
    assert sleep.delays == []
