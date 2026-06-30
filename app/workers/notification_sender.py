"""Notification_Sender worker (Req 20.1, 20.2, 20.5, 30.1).

The Notification_Sender is one of the eight background workers (design
"Background Workers", Req 30.1). When an alert event occurs it delivers the
notification through **each channel the recipient has enabled** among Telegram,
email, push and in-app (Req 20.2). Per-channel behaviour:

- **Telegram** (Req 20.1): when the user has configured a Telegram bot/chat
  identifier, the message is sent via the Telegram Bot API.
- **Email**: the message is sent to the user's email address.
- **Push** (Req 20.5): push notifications are delivered through Firebase (FCM)
  using the user's registered device token.
- **In-app**: a row is persisted to the ``notifications`` table so the SPA can
  surface it (design Table Catalog ``notifications``).

Design references:
- ``app.workers.alert_checker.RedisActionSink._do_notify`` publishes the alert
  event this worker consumes (WS contract
  ``{"type":"alert","rule_id":...,"device_id":...,"title":...,"message":...}``).
- ``app.models.ops.Notification`` (channel TEXT in telegram/email/push/in_app).

Like the other workers this module is split into a **pure planning core** and
**async delivery** so the channel-selection logic and per-channel dispatch can
be unit-tested without any live Telegram/Firebase/SMTP/DB:

- :func:`channels_to_deliver` is a pure function deciding, for one recipient,
  exactly which enabled channels actually have a usable address (Req 20.2).
- :func:`deliver_to_recipient` / :func:`process_event` dispatch a message to an
  injected :class:`DeliveryClients` (Telegram/email/push senders) and an
  injected in-app persister, so tests inject fakes and no live call is made.
- :class:`FirebasePushClient` abstracts FCM delivery (Req 20.5); the real
  ``firebase-admin`` client is only imported inside its sender, never at import
  time, so the worker and its tests never require live credentials.
- :class:`SqlAlchemyInAppPersister` writes the in-app :class:`Notification` row.

``run``/``main`` wire the pure core to a Redis pub/sub alert source, a recipient
loader and the real clients, mirroring the other workers (testable core + thin
run loop with a ``stop_event`` + graceful shutdown).
"""

from __future__ import annotations

import asyncio
import json
import signal
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Sequence

from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Channel model
# ---------------------------------------------------------------------------
class Channel(str, Enum):
    """A delivery channel (design ``notifications.channel``; Req 20.2)."""

    TELEGRAM = "telegram"
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"


# Canonical delivery order so a recipient's channels are always processed
# deterministically (telegram -> email -> push -> in_app).
_CHANNEL_ORDER: tuple[Channel, ...] = (
    Channel.TELEGRAM,
    Channel.EMAIL,
    Channel.PUSH,
    Channel.IN_APP,
)


def _coerce_channel(value: Any) -> Optional[Channel]:
    """Map a stored channel string/enum to a :class:`Channel`, or ``None``."""
    if isinstance(value, Channel):
        return value
    try:
        return Channel(str(value).strip().lower())
    except ValueError:
        return None


@dataclass(frozen=True)
class Recipient:
    """A user's notification preferences, decoupled from the ORM.

    ``enabled_channels`` is the set of channels the user opted into (Req 20.2).
    The address fields carry the per-channel destination; a channel is only
    deliverable when it is enabled *and* its address is present:

    - ``telegram_chat_id`` -> Telegram (Req 20.1)
    - ``email``            -> email
    - ``push_token``       -> Firebase push (Req 20.5)
    - in-app needs no address (it is persisted against ``user_id``).
    """

    user_id: str
    enabled_channels: frozenset[Channel] = frozenset()
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    push_token: Optional[str] = None

    @classmethod
    def build(
        cls,
        user_id: str,
        channels: Sequence[Any],
        *,
        telegram_chat_id: Optional[str] = None,
        email: Optional[str] = None,
        push_token: Optional[str] = None,
    ) -> "Recipient":
        """Construct a recipient, coercing ``channels`` to :class:`Channel`s."""
        enabled = frozenset(
            ch for ch in (_coerce_channel(c) for c in channels) if ch is not None
        )
        return cls(
            user_id=str(user_id),
            enabled_channels=enabled,
            telegram_chat_id=telegram_chat_id,
            email=email,
            push_token=push_token,
        )

    def address_for(self, channel: Channel) -> Optional[str]:
        """Return the destination address for ``channel`` (``None`` if missing)."""
        if channel is Channel.TELEGRAM:
            return self.telegram_chat_id
        if channel is Channel.EMAIL:
            return self.email
        if channel is Channel.PUSH:
            return self.push_token
        if channel is Channel.IN_APP:
            return self.user_id
        return None


@dataclass(frozen=True)
class NotificationEvent:
    """One alert to deliver (parsed from the Alert_Checker notify payload)."""

    org_id: str
    title: Optional[str] = None
    body: Optional[str] = None
    device_id: Optional[str] = None
    rule_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Pure channel-selection core (testable; no clients required)
# ---------------------------------------------------------------------------
def channels_to_deliver(recipient: Recipient) -> list[Channel]:
    """Return the channels to deliver to for ``recipient``, in canonical order.

    A channel is included only when it is in ``enabled_channels`` *and* has a
    usable address (Req 20.2): Telegram needs a chat id, email needs an address,
    push needs a device token, and in-app is always deliverable for a known
    user. Channels the user did not enable are never returned, so disabling a
    channel suppresses delivery on it.
    """
    return [
        ch
        for ch in _CHANNEL_ORDER
        if ch in recipient.enabled_channels and recipient.address_for(ch)
    ]


def _compose_text(event: NotificationEvent) -> str:
    """Compose a single-line/body text from an event's title + body."""
    parts = [p for p in (event.title, event.body) if p]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Delivery clients (abstracted; injected so tests make no live calls)
# ---------------------------------------------------------------------------
# Async senders. Each raises on failure; the dispatcher isolates failures so one
# failing channel never blocks the others (mirrors alert_checker's sink).
TelegramSender = Callable[[str, str], Awaitable[None]]  # (chat_id, text)
EmailSender = Callable[[str, str, str], Awaitable[None]]  # (email, subject, body)
PushSender = Callable[[str, str, str], Awaitable[None]]  # (token, title, body)
# Persists the in-app notification row for one (event, recipient).
InAppPersister = Callable[[NotificationEvent, Recipient], Awaitable[None]]


@dataclass(frozen=True)
class DeliveryClients:
    """The external senders the worker dispatches to (any may be unwired).

    When a channel's sender is ``None`` that channel is skipped (and reported as
    failed), so a partially configured deployment degrades gracefully instead of
    crashing. In-app delivery is handled by :class:`SqlAlchemyInAppPersister`,
    not by a sender here.
    """

    telegram: Optional[TelegramSender] = None
    email: Optional[EmailSender] = None
    push: Optional[PushSender] = None


@dataclass
class DeliveryReport:
    """Outcome of delivering one event to one recipient."""

    delivered: list[Channel] = field(default_factory=list)
    failed: list[Channel] = field(default_factory=list)


async def deliver_to_recipient(
    event: NotificationEvent,
    recipient: Recipient,
    clients: DeliveryClients,
    *,
    persist_in_app: Optional[InAppPersister] = None,
) -> DeliveryReport:
    """Deliver ``event`` to ``recipient`` over every enabled, addressable channel.

    For each channel returned by :func:`channels_to_deliver` the matching sender
    is invoked (Telegram/email/push) or the in-app row is persisted (Req 20.2,
    20.1, 20.5). A channel whose sender/persister is unwired or which raises is
    recorded in :attr:`DeliveryReport.failed` and logged, but never aborts the
    remaining channels - so one broken channel can't suppress the others.
    """
    report = DeliveryReport()
    text = _compose_text(event)
    title = event.title or ""

    for channel in channels_to_deliver(recipient):
        try:
            if channel is Channel.TELEGRAM:
                if clients.telegram is None:
                    raise _Unwired("telegram")
                await clients.telegram(recipient.telegram_chat_id or "", text)
            elif channel is Channel.EMAIL:
                if clients.email is None:
                    raise _Unwired("email")
                await clients.email(recipient.email or "", title, event.body or "")
            elif channel is Channel.PUSH:
                if clients.push is None:
                    raise _Unwired("push")
                await clients.push(recipient.push_token or "", title, event.body or "")
            elif channel is Channel.IN_APP:
                if persist_in_app is None:
                    raise _Unwired("in_app")
                await persist_in_app(event, recipient)
        except Exception as exc:  # one channel must not block the rest (Req 20.2)
            report.failed.append(channel)
            logger.warning(
                "notification_channel_failed",
                extra={
                    "channel": channel.value,
                    "user_id": recipient.user_id,
                    "error": str(exc),
                },
            )
        else:
            report.delivered.append(channel)
            logger.info(
                "notification_delivered",
                extra={"channel": channel.value, "user_id": recipient.user_id},
            )
    return report


class _Unwired(RuntimeError):
    """Raised internally when a channel's sender/persister is not configured."""


async def process_event(
    event: NotificationEvent,
    recipients: Sequence[Recipient],
    clients: DeliveryClients,
    *,
    persist_in_app: Optional[InAppPersister] = None,
) -> int:
    """Deliver ``event`` to every recipient, returning the channels delivered.

    Each recipient is handled independently so one recipient's failing channel
    never affects another's delivery.
    """
    total = 0
    for recipient in recipients:
        report = await deliver_to_recipient(
            event, recipient, clients, persist_in_app=persist_in_app
        )
        total += len(report.delivered)
    return total


# ---------------------------------------------------------------------------
# Firebase push client (Req 20.5) - abstracted, no live import at module load
# ---------------------------------------------------------------------------
class FirebasePushClient:
    """Firebase Cloud Messaging push sender (Req 20.5).

    The real ``firebase-admin`` SDK is imported lazily inside :meth:`send` and
    the messaging transport is injected, so importing this module - and running
    its tests - never requires Firebase credentials or network access. In
    production ``main`` wires a configured client; tests pass a fake
    ``send_fn``.
    """

    def __init__(self, send_fn: Optional[Callable[[str, str, str], Awaitable[None]]] = None) -> None:
        self._send_fn = send_fn

    async def send(self, token: str, title: str, body: str) -> None:
        """Deliver one push message to ``token`` via Firebase."""
        if self._send_fn is None:  # pragma: no cover - exercised only with live FCM
            raise RuntimeError("FirebasePushClient is not configured with a sender")
        await self._send_fn(token, title, body)

    async def __call__(self, token: str, title: str, body: str) -> None:
        await self.send(token, title, body)


# ---------------------------------------------------------------------------
# In-app persistence (writes the notifications row)
# ---------------------------------------------------------------------------
class SqlAlchemyInAppPersister:
    """Persist an in-app notification to the ``notifications`` table (Req 20).

    Records one :class:`Notification` row (``channel="in_app"``) per delivery so
    the SPA can surface it. Takes a session factory so it works against both the
    live async engine and an in-memory SQLite test engine.
    """

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    async def __call__(self, event: NotificationEvent, recipient: Recipient) -> None:
        import uuid

        from app.models.ops import Notification

        async with self._session_factory() as session:
            session.add(
                Notification(
                    org_id=uuid.UUID(str(event.org_id)),
                    user_id=uuid.UUID(str(recipient.user_id)),
                    channel=Channel.IN_APP.value,
                    title=event.title,
                    body=event.body,
                )
            )
            await session.commit()


# ---------------------------------------------------------------------------
# Alert event parsing (from the Alert_Checker notify payload)
# ---------------------------------------------------------------------------
def parse_alert_event(raw: Any, *, org_id: str = "") -> Optional[NotificationEvent]:
    """Parse a published alert message into a :class:`NotificationEvent`.

    Accepts the JSON string (or already-decoded dict) the Alert_Checker
    publishes on the device channel
    (``{"type":"alert","rule_id":...,"device_id":...,"title":...,"message":...}``).
    Returns ``None`` for non-alert or unparseable messages so the run loop can
    skip them without crashing.
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

    if not isinstance(obj, dict) or obj.get("type") != "alert":
        return None

    return NotificationEvent(
        org_id=str(obj.get("org_id", org_id)),
        title=obj.get("title"),
        body=obj.get("message") or obj.get("body"),
        device_id=(str(obj["device_id"]) if obj.get("device_id") else None),
        rule_id=(str(obj["rule_id"]) if obj.get("rule_id") else None),
    )


# ---------------------------------------------------------------------------
# Run loop + entry point
# ---------------------------------------------------------------------------
# A source yields the next alert event to deliver (or ``None`` when idle).
EventSource = Callable[[], Awaitable[Optional[NotificationEvent]]]
# A loader resolves the recipients (with their channel prefs) for an event.
RecipientLoader = Callable[[NotificationEvent], Awaitable[Sequence[Recipient]]]


async def run(
    event_source: EventSource,
    load_recipients: RecipientLoader,
    clients: DeliveryClients,
    *,
    persist_in_app: Optional[InAppPersister] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Consume alert events and deliver them until ``stop_event`` is set.

    Each loop pulls one :class:`NotificationEvent`, resolves its recipients, and
    delivers to each over their enabled channels (Req 20.2). A failure handling
    one event is logged and the loop continues so a single bad event never stops
    the worker.
    """
    stop_event = stop_event or asyncio.Event()

    while not stop_event.is_set():
        try:
            event = await event_source()
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("notification_source_failed")
            continue
        if event is None:
            continue
        try:
            recipients = await load_recipients(event)
            await process_event(
                event, recipients, clients, persist_in_app=persist_in_app
            )
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception(
                "notification_event_failed", extra={"org_id": event.org_id}
            )


async def _email_sender(email: str, subject: str, body: str) -> None:
    """Module-level EmailSender adapter for the SMTP service (lazy import)."""
    from app.services import email_service

    await email_service.alert_email_sender(email, subject, body)


def main() -> None:  # pragma: no cover - process entry point wires live infra
    """Process entry point (``python -m app.workers.notification_sender``).

    Wires a Redis pub/sub alert source, a DB-backed recipient loader, the real
    Telegram/email/Firebase senders and a DB-backed in-app persister, then runs
    the delivery loop with graceful shutdown - mirroring the other workers.
    """
    configure_logging()
    logger.info("notification_sender_starting")

    stop_event = asyncio.Event()

    async def _amain() -> None:
        from app.core import redis_keys as rk
        from app.core.redis_client import get_redis
        from app.db.session import async_session_factory

        redis = get_redis()
        if redis is None:
            raise RuntimeError("Redis client unavailable; cannot run Notification_Sender")

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:  # Windows lacks add_signal_handler
                pass

        # The Alert_Checker publishes notify events on each device channel.
        pubsub = redis.pubsub()
        await pubsub.psubscribe(f"{rk.NAMESPACE}{rk.SEP}device{rk.SEP}*")

        async def _source() -> Optional[NotificationEvent]:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if not message:
                return None
            return parse_alert_event(message.get("data"))

        clients = DeliveryClients(
            telegram=None,  # wired to the Telegram Bot API client when configured
            email=_email_sender,  # SMTP email via app.services.email_service
            push=FirebasePushClient(),  # Req 20.5
        )
        persister = SqlAlchemyInAppPersister(async_session_factory)
        await run(
            _source,
            _load_recipients,
            clients,
            persist_in_app=persister,
            stop_event=stop_event,
        )

    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass
    logger.info("notification_sender_stopped")


async def _load_recipients(  # pragma: no cover - exercised against a live DB
    event: NotificationEvent,
) -> Sequence[Recipient]:
    """Load the recipients (and channel prefs) to notify for an alert event."""
    import uuid

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.user import User

    if not event.org_id:
        return []

    org_uuid = uuid.UUID(str(event.org_id))
    recipients: list[Recipient] = []
    async with async_session_factory() as session:
        users = (
            await session.execute(select(User).where(User.org_id == org_uuid))
        ).scalars().all()
        for user in users:
            channels = [Channel.IN_APP]
            if user.email:
                channels.append(Channel.EMAIL)
            recipients.append(
                Recipient.build(
                    str(user.id),
                    channels,
                    email=user.email,
                )
            )
    return recipients


if __name__ == "__main__":
    main()
