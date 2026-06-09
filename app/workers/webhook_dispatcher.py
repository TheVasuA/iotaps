"""Webhook_Dispatcher worker (Req 20.3, 20.4, 30.1).

The Webhook_Dispatcher is one of the eight background workers (design
"Background Workers", Req 30.1). When an event configured with a webhook occurs
it sends an HTTP POST to the configured external URL carrying the event payload
(Req 20.3). If a delivery attempt fails it retries according to the webhook's
configured retry policy, backing off between attempts, and marks the delivery
failed once the maximum number of attempts is exhausted (Req 20.4).

Event source / contract:
- ``app.workers.alert_checker.RedisActionSink._do_webhook`` publishes the event
  this worker consumes on the device pub/sub channel as
  ``{"type":"webhook","rule_id":...,"device_id":...,"url":...,"payload":...}``.
- ``app.models.ops.Webhook`` stores the per-org configuration
  (``event_type``/``url``/``secret``/``retry_policy`` JSONB); the
  ``retry_policy`` drives :class:`RetryPolicy` here.

Like the other workers this module is split into a **pure core** and an **async
delivery** path so the retry/backoff logic can be unit- and property-tested
without any live network:

- :class:`RetryPolicy` (+ :meth:`RetryPolicy.from_config`) is the pure model of
  the configured retry behaviour: how many attempts to make and how long to wait
  before each retry (exponential backoff capped at a maximum).
- :func:`parse_webhook_event` turns the Alert_Checker payload into a
  :class:`WebhookEvent`.
- :func:`deliver_webhook` performs the POST-with-retry against an injected
  :data:`HttpPoster`, awaiting an injected ``sleep_fn`` for each backoff, and
  returns a :class:`DeliveryResult` recording the outcome (Req 20.3, 20.4). It
  never makes a live call itself - tests inject a fake poster.
- :class:`HttpxPoster` abstracts the real HTTP client; ``httpx`` is imported
  lazily inside it so importing this module (and its tests) needs no network.

``run``/``main`` wire the pure core to a Redis pub/sub event source and the real
HTTP poster, mirroring the other workers (testable core + thin run loop with a
``stop_event`` + graceful shutdown).
"""

from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Retry policy (pure; testable without any network)
# ---------------------------------------------------------------------------
# Defaults applied when a webhook has no (or a partial) ``retry_policy`` config.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_INITIAL_SECONDS = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_BACKOFF_MAX_SECONDS = 60.0


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to attempt a delivery and how long to wait between tries.

    Models the webhook's configured ``retry_policy`` (Req 20.4):

    - ``max_attempts``: total number of delivery attempts (the first try plus
      retries). Always at least 1 so a delivery is attempted at least once.
    - ``backoff_initial``: seconds to wait before the *first* retry.
    - ``backoff_factor``: multiplier applied to the wait for each subsequent
      retry (exponential backoff). A factor of 1 yields a constant delay.
    - ``backoff_max``: upper bound on any single wait, so backoff can't grow
      without limit.

    Backoff is bounded and deterministic so the schedule is fully testable.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_initial: float = DEFAULT_BACKOFF_INITIAL_SECONDS
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    backoff_max: float = DEFAULT_BACKOFF_MAX_SECONDS

    @classmethod
    def from_config(cls, config: Any) -> "RetryPolicy":
        """Build a policy from a webhook's ``retry_policy`` JSONB (or ``None``).

        Unknown/missing/invalid fields fall back to the defaults so a malformed
        or absent policy still yields a usable, bounded schedule. Accepts a few
        common key spellings (``max_attempts``/``max_retries``/``attempts``,
        ``backoff``/``backoff_initial``/``initial_delay``, ``factor``/
        ``multiplier``, ``backoff_max``/``max_backoff``) so editor and
        hand-written configs both work.
        """
        if not isinstance(config, dict):
            return cls()

        max_attempts = _coerce_int(
            _first(config, "max_attempts", "max_retries", "attempts"),
            DEFAULT_MAX_ATTEMPTS,
        )
        # ``max_retries`` is the number of retries *after* the first attempt;
        # ``max_attempts`` is the total. Treat a ``max_retries`` spelling as
        # retries-after-first so a config of {"max_retries": 3} -> 4 attempts.
        if (
            "max_attempts" not in config
            and "attempts" not in config
            and "max_retries" in config
        ):
            max_attempts = max_attempts + 1

        backoff_initial = _coerce_float(
            _first(config, "backoff_initial", "backoff", "initial_delay", "delay"),
            DEFAULT_BACKOFF_INITIAL_SECONDS,
        )
        backoff_factor = _coerce_float(
            _first(config, "backoff_factor", "factor", "multiplier"),
            DEFAULT_BACKOFF_FACTOR,
        )
        backoff_max = _coerce_float(
            _first(config, "backoff_max", "max_backoff", "max_delay"),
            DEFAULT_BACKOFF_MAX_SECONDS,
        )

        return cls(
            max_attempts=max(1, max_attempts),
            backoff_initial=max(0.0, backoff_initial),
            backoff_factor=max(0.0, backoff_factor),
            backoff_max=max(0.0, backoff_max),
        )

    def backoff_for_retry(self, retry_index: int) -> float:
        """Seconds to wait before the retry numbered ``retry_index`` (0-based).

        ``retry_index`` 0 is the wait before the first retry (after attempt 1),
        index 1 is before the second retry, and so on:

            delay(i) = min(backoff_initial * backoff_factor**i, backoff_max)

        The result is always within ``[0, backoff_max]``.
        """
        if retry_index < 0:
            return 0.0
        delay = self.backoff_initial * (self.backoff_factor ** retry_index)
        return max(0.0, min(delay, self.backoff_max))


def _first(config: dict[str, Any], *keys: str) -> Any:
    """Return the first present key's value from ``config`` (or ``None``)."""
    for key in keys:
        if key in config:
            return config[key]
    return None


def _coerce_int(value: Any, default: int) -> int:
    """Coerce ``value`` to an int, falling back to ``default``."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    """Coerce ``value`` to a float, falling back to ``default``."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Webhook event model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WebhookEvent:
    """One webhook delivery to perform (parsed from the Alert_Checker payload).

    ``url`` is the configured external endpoint, ``payload`` is the JSON body to
    POST (Req 20.3). ``retry_policy`` carries the per-webhook policy config so
    the dispatcher honours the *configured* policy (Req 20.4); ``secret`` is an
    optional shared secret used to sign the request.
    """

    url: str
    payload: dict[str, Any]
    retry_policy: Optional[dict[str, Any]] = None
    secret: Optional[str] = None
    event_type: Optional[str] = None
    rule_id: Optional[str] = None
    device_id: Optional[str] = None

    def policy(self) -> RetryPolicy:
        """The :class:`RetryPolicy` for this event (defaults when unconfigured)."""
        return RetryPolicy.from_config(self.retry_policy)


def parse_webhook_event(raw: Any) -> Optional[WebhookEvent]:
    """Parse a published message into a :class:`WebhookEvent`, or ``None``.

    Accepts the JSON string/bytes (or already-decoded dict) the Alert_Checker
    publishes on the device channel
    (``{"type":"webhook","url":...,"payload":...}``). Returns ``None`` for
    non-webhook messages, unparseable data, or a message with no ``url`` so the
    run loop can skip them without crashing.
    """
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            return None
    elif isinstance(raw, dict):
        obj = raw
    else:
        return None

    if not isinstance(obj, dict) or obj.get("type") != "webhook":
        return None

    url = obj.get("url")
    if not url or not isinstance(url, str):
        return None

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        payload = {} if payload is None else {"data": payload}

    retry_policy = obj.get("retry_policy")
    if not isinstance(retry_policy, dict):
        retry_policy = None

    return WebhookEvent(
        url=url,
        payload=payload,
        retry_policy=retry_policy,
        secret=(str(obj["secret"]) if obj.get("secret") else None),
        event_type=(str(obj["event_type"]) if obj.get("event_type") else None),
        rule_id=(str(obj["rule_id"]) if obj.get("rule_id") else None),
        device_id=(str(obj["device_id"]) if obj.get("device_id") else None),
    )


# ---------------------------------------------------------------------------
# HTTP poster abstraction (injected so tests make no live calls)
# ---------------------------------------------------------------------------
# An async poster sends an HTTP POST of ``payload`` to ``url`` with optional
# headers and returns the response status code. It raises on a transport/
# connection failure (treated the same as a non-2xx response: a failed attempt).
HttpPoster = Callable[[str, dict[str, Any], Optional[dict[str, str]]], Awaitable[int]]


def is_success(status_code: int) -> bool:
    """Whether an HTTP status code counts as a successful delivery (2xx)."""
    return 200 <= status_code < 300


@dataclass
class DeliveryResult:
    """Outcome of attempting to deliver one webhook (Req 20.3, 20.4).

    ``delivered`` is ``True`` when an attempt returned a 2xx status.
    ``attempts`` is how many attempts were actually made (1..max_attempts).
    ``failed`` is ``True`` only when every attempt was exhausted without success
    - i.e. the delivery is marked failed after the maximum attempts (Req 20.4).
    ``last_status`` is the status code of the final attempt (``None`` if every
    attempt raised before a response).
    """

    delivered: bool = False
    attempts: int = 0
    last_status: Optional[int] = None

    @property
    def failed(self) -> bool:
        """True when the delivery was exhausted without a successful attempt."""
        return not self.delivered


# ---------------------------------------------------------------------------
# Delivery with retry/backoff (async; injected poster + sleep)
# ---------------------------------------------------------------------------
async def deliver_webhook(
    event: WebhookEvent,
    poster: HttpPoster,
    *,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_failed: Optional[Callable[[WebhookEvent, "DeliveryResult"], Awaitable[None]]] = None,
) -> DeliveryResult:
    """POST an event's payload to its URL, retrying per the configured policy.

    Performs up to ``policy.max_attempts`` attempts (Req 20.4). Each attempt
    POSTs ``event.payload`` to ``event.url`` via ``poster`` (Req 20.3); an
    attempt succeeds when it returns a 2xx status, in which case delivery stops
    immediately. A non-2xx status or a raised transport error counts as a failed
    attempt: the dispatcher waits ``policy.backoff_for_retry(i)`` (awaiting
    ``sleep_fn``) and retries, the wait growing with exponential backoff up to
    the policy's cap. After the final attempt fails the delivery is marked failed
    (``result.failed``) and the injected ``on_failed`` callback (if any) is
    invoked so the failure can be persisted/recorded.

    Returns a :class:`DeliveryResult` describing the outcome. Never raises for a
    delivery failure - the result captures it.
    """
    policy = event.policy()
    headers = _build_headers(event)
    result = DeliveryResult()

    for attempt in range(1, policy.max_attempts + 1):
        result.attempts = attempt
        try:
            status = await poster(event.url, event.payload, headers)
            result.last_status = status
            if is_success(status):
                result.delivered = True
                logger.info(
                    "webhook_delivered",
                    extra={
                        "url": event.url,
                        "status": status,
                        "attempt": attempt,
                        "rule_id": event.rule_id,
                    },
                )
                return result
            logger.warning(
                "webhook_attempt_failed",
                extra={"url": event.url, "status": status, "attempt": attempt},
            )
        except Exception as exc:
            result.last_status = None
            logger.warning(
                "webhook_attempt_error",
                extra={"url": event.url, "attempt": attempt, "error": str(exc)},
            )

        # Back off before the next retry, unless this was the final attempt.
        if attempt < policy.max_attempts:
            delay = policy.backoff_for_retry(attempt - 1)
            if delay > 0:
                await sleep_fn(delay)

    # Every attempt was exhausted without a 2xx response (Req 20.4).
    logger.error(
        "webhook_delivery_failed",
        extra={
            "url": event.url,
            "attempts": result.attempts,
            "last_status": result.last_status,
            "rule_id": event.rule_id,
        },
    )
    if on_failed is not None:
        try:
            await on_failed(event, result)
        except Exception:  # pragma: no cover - recording failure must not crash
            logger.exception("webhook_mark_failed_error", extra={"url": event.url})
    return result


def _build_headers(event: WebhookEvent) -> dict[str, str]:
    """Build request headers, signing the body when a secret is configured.

    Always sends ``Content-Type: application/json``. When ``event.secret`` is
    set, an HMAC-SHA256 signature of the JSON body is added as
    ``X-IoTAPS-Signature`` so the receiver can verify authenticity (mirrors the
    Razorpay webhook signature pattern used elsewhere in the platform).
    """
    headers = {"Content-Type": "application/json"}
    if event.secret:
        import hashlib
        import hmac

        body = json.dumps(event.payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(
            event.secret.encode(), body, hashlib.sha256
        ).hexdigest()
        headers["X-IoTAPS-Signature"] = signature
    return headers


# ---------------------------------------------------------------------------
# Default httpx-backed poster (Req 20.3) - no live import at module load
# ---------------------------------------------------------------------------
class HttpxPoster:
    """Default :data:`HttpPoster` that POSTs via ``httpx`` (Req 20.3).

    ``httpx`` is imported lazily inside :meth:`__call__` so importing this module
    - and running its tests - never requires the HTTP client or any network. The
    timeout bounds each attempt so a hung endpoint cannot stall the worker.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def __call__(
        self,
        url: str,
        payload: dict[str, Any],
        headers: Optional[dict[str, str]] = None,
    ) -> int:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.status_code


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
# A source yields the next webhook event to deliver (or ``None`` when idle).
EventSource = Callable[[], Awaitable[Optional[WebhookEvent]]]


async def run(
    event_source: EventSource,
    poster: HttpPoster,
    *,
    stop_event: Optional[asyncio.Event] = None,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_failed: Optional[Callable[[WebhookEvent, DeliveryResult], Awaitable[None]]] = None,
) -> None:
    """Consume webhook events and deliver them until ``stop_event`` is set.

    Each loop pulls one :class:`WebhookEvent` and delivers it via
    :func:`deliver_webhook` (POST + retry/backoff per the configured policy).
    Each event is dispatched to its own task so one event's backoff waits do not
    stall delivery of subsequent events. A failure handling one event is logged
    and the loop continues so a single bad event never stops the worker.
    """
    stop_event = stop_event or asyncio.Event()
    pending: set[asyncio.Task[Any]] = set()

    while not stop_event.is_set():
        try:
            event = await event_source()
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("webhook_source_failed")
            continue
        if event is None:
            continue

        async def _handle(ev: WebhookEvent) -> None:
            try:
                await deliver_webhook(
                    ev, poster, sleep_fn=sleep_fn, on_failed=on_failed
                )
            except Exception:  # pragma: no cover - keep the loop alive
                logger.exception("webhook_event_failed", extra={"url": ev.url})

        task = asyncio.ensure_future(_handle(event))
        pending.add(task)
        task.add_done_callback(pending.discard)

    # Drain in-flight deliveries (including pending backoffs) before exiting.
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def main() -> None:  # pragma: no cover - process entry point wires live infra
    """Process entry point (``python -m app.workers.webhook_dispatcher``).

    Wires a Redis pub/sub webhook-event source and the real httpx poster, then
    runs the delivery loop with graceful shutdown - mirroring the other workers.
    """
    configure_logging()
    logger.info("webhook_dispatcher_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        from app.core import redis_keys as rk
        from app.core.redis_client import get_redis

        redis = get_redis()
        if redis is None:
            raise RuntimeError("Redis client unavailable; cannot run Webhook_Dispatcher")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass

        # The Alert_Checker publishes webhook events on each device channel.
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"{rk.NAMESPACE}{rk.SEP}device{rk.SEP}*")

        async def _source() -> Optional[WebhookEvent]:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if not message:
                return None
            return parse_webhook_event(message.get("data"))

        await run(_source, HttpxPoster(), stop_event=stop_event)

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("webhook_dispatcher_stopped")


if __name__ == "__main__":
    main()
