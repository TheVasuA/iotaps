"""Unit tests for the Notification_Sender worker (Task 19.1, Req 20.1, 20.2, 20.5, 30.1).

These exercise the pure channel-selection core and the async dispatcher with
injected fakes (no live Telegram/Firebase/SMTP), plus the in-app persister
against an in-memory SQLite DB:

- only enabled + addressable channels are delivered to (Req 20.2)
- each channel routes to its matching sender (Telegram/email/push) (Req 20.1, 20.5)
- in-app notifications are persisted to the ``notifications`` table (Req 20)
- one failing/unwired channel never blocks the others (Req 20.2)
- the run loop delivers an event and stops promptly on its event
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import ColumnDefault

from app.db.base import Base
from app.models.ops import Notification
from app.models.organization import Organization
from app.models.user import User
from app.workers import notification_sender as ns

import app.models  # noqa: F401  (register all models on Base.metadata)


# ---------------------------------------------------------------------------
# Fakes capturing what each channel was asked to send
# ---------------------------------------------------------------------------
class _Recorder:
    def __init__(self) -> None:
        self.telegram: list[tuple[str, str]] = []
        self.email: list[tuple[str, str, str]] = []
        self.push: list[tuple[str, str, str]] = []
        self.in_app: list[tuple[ns.NotificationEvent, ns.Recipient]] = []

    async def send_telegram(self, chat_id: str, text: str) -> None:
        self.telegram.append((chat_id, text))

    async def send_email(self, email: str, subject: str, body: str) -> None:
        self.email.append((email, subject, body))

    async def send_push(self, token: str, title: str, body: str) -> None:
        self.push.append((token, title, body))

    async def persist_in_app(self, event: ns.NotificationEvent, recipient: ns.Recipient) -> None:
        self.in_app.append((event, recipient))

    def clients(self) -> ns.DeliveryClients:
        return ns.DeliveryClients(
            telegram=self.send_telegram,
            email=self.send_email,
            push=self.send_push,
        )


def _event() -> ns.NotificationEvent:
    return ns.NotificationEvent(
        org_id="org-1", title="High temp", body="Sensor over 30C", device_id="dev-1", rule_id="rule-1"
    )


# ---------------------------------------------------------------------------
# Pure channel-selection core (Req 20.2)
# ---------------------------------------------------------------------------
def test_channels_to_deliver_only_enabled_and_addressable():
    """A channel is delivered only when enabled AND it has a usable address."""
    recipient = ns.Recipient.build(
        "user-1",
        [ns.Channel.TELEGRAM, ns.Channel.EMAIL, ns.Channel.PUSH, ns.Channel.IN_APP],
        telegram_chat_id="123",
        email="u@example.com",
        push_token="tok",
    )
    assert ns.channels_to_deliver(recipient) == [
        ns.Channel.TELEGRAM,
        ns.Channel.EMAIL,
        ns.Channel.PUSH,
        ns.Channel.IN_APP,
    ]


def test_channels_to_deliver_skips_disabled_channels():
    """Channels the user did not enable are never delivered to (Req 20.2)."""
    recipient = ns.Recipient.build(
        "user-1",
        [ns.Channel.EMAIL, ns.Channel.IN_APP],
        telegram_chat_id="123",  # present but NOT enabled -> excluded
        email="u@example.com",
        push_token="tok",  # present but NOT enabled -> excluded
    )
    assert ns.channels_to_deliver(recipient) == [ns.Channel.EMAIL, ns.Channel.IN_APP]


def test_channels_to_deliver_skips_enabled_without_address():
    """An enabled channel with no address is not deliverable."""
    recipient = ns.Recipient.build(
        "user-1",
        [ns.Channel.TELEGRAM, ns.Channel.PUSH, ns.Channel.IN_APP],
        # no telegram_chat_id, no push_token
    )
    # Telegram + push lack addresses; in-app always works for a known user.
    assert ns.channels_to_deliver(recipient) == [ns.Channel.IN_APP]


def test_recipient_build_ignores_unknown_channels():
    """Unknown channel strings are dropped rather than crashing."""
    recipient = ns.Recipient.build("user-1", ["email", "sms", "in_app"], email="u@x.com")
    assert recipient.enabled_channels == frozenset({ns.Channel.EMAIL, ns.Channel.IN_APP})


# ---------------------------------------------------------------------------
# Dispatch routing (Req 20.1, 20.5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliver_routes_each_channel_to_its_sender():
    """Each enabled channel routes to its matching sender with the right address."""
    rec = _Recorder()
    recipient = ns.Recipient.build(
        "user-1",
        [ns.Channel.TELEGRAM, ns.Channel.EMAIL, ns.Channel.PUSH],
        telegram_chat_id="chat-9",
        email="u@example.com",
        push_token="push-tok",
    )
    report = await ns.deliver_to_recipient(_event(), recipient, rec.clients())

    assert report.delivered == [ns.Channel.TELEGRAM, ns.Channel.EMAIL, ns.Channel.PUSH]
    assert report.failed == []
    assert rec.telegram == [("chat-9", "High temp\nSensor over 30C")]
    assert rec.email == [("u@example.com", "High temp", "Sensor over 30C")]
    assert rec.push == [("push-tok", "High temp", "Sensor over 30C")]


@pytest.mark.asyncio
async def test_one_failing_channel_does_not_block_others():
    """A raising sender is recorded as failed but the other channels still run."""
    rec = _Recorder()

    async def boom(*args) -> None:
        raise RuntimeError("telegram down")

    clients = ns.DeliveryClients(telegram=boom, email=rec.send_email, push=rec.send_push)
    recipient = ns.Recipient.build(
        "user-1",
        [ns.Channel.TELEGRAM, ns.Channel.EMAIL],
        telegram_chat_id="c",
        email="u@example.com",
    )
    report = await ns.deliver_to_recipient(_event(), recipient, clients)

    assert ns.Channel.TELEGRAM in report.failed
    assert report.delivered == [ns.Channel.EMAIL]
    assert rec.email == [("u@example.com", "High temp", "Sensor over 30C")]


@pytest.mark.asyncio
async def test_unwired_channel_is_reported_failed_not_raised():
    """An enabled channel with no configured sender fails gracefully."""
    recipient = ns.Recipient.build("user-1", [ns.Channel.PUSH], push_token="tok")
    # clients has push=None
    report = await ns.deliver_to_recipient(_event(), recipient, ns.DeliveryClients())
    assert report.delivered == []
    assert report.failed == [ns.Channel.PUSH]


# ---------------------------------------------------------------------------
# Firebase push abstraction (Req 20.5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_firebase_push_client_delegates_to_injected_sender():
    """FirebasePushClient forwards to the injected transport (no live FCM)."""
    sent: list[tuple[str, str, str]] = []

    async def fake_send(token: str, title: str, body: str) -> None:
        sent.append((token, title, body))

    client = ns.FirebasePushClient(fake_send)
    await client("tok", "T", "B")
    assert sent == [("tok", "T", "B")]


@pytest.mark.asyncio
async def test_firebase_push_client_unconfigured_raises():
    """An unconfigured Firebase client raises rather than calling live FCM."""
    with pytest.raises(RuntimeError):
        await ns.FirebasePushClient().send("tok", "T", "B")


# ---------------------------------------------------------------------------
# Alert event parsing
# ---------------------------------------------------------------------------
def test_parse_alert_event_from_alert_checker_payload():
    raw = (
        '{"type":"alert","rule_id":"r1","device_id":"d1",'
        '"org_id":"org-1","title":"Hot","message":"too hot"}'
    )
    event = ns.parse_alert_event(raw)
    assert event is not None
    assert event.org_id == "org-1"
    assert event.title == "Hot"
    assert event.body == "too hot"
    assert event.device_id == "d1"
    assert event.rule_id == "r1"


def test_parse_alert_event_ignores_non_alert_and_garbage():
    assert ns.parse_alert_event('{"type":"status"}') is None
    assert ns.parse_alert_event("not-json") is None
    assert ns.parse_alert_event(42) is None


# ---------------------------------------------------------------------------
# In-app persistence against SQLite (Req 20)
# ---------------------------------------------------------------------------
_TABLES = [Organization.__table__, User.__table__, Notification.__table__]


def _prepare_tables() -> None:
    for table in _TABLES:
        if "id" in table.c:
            col = table.c.id
            col.server_default = None
            col.default = ColumnDefault(lambda: uuid.uuid4())


@pytest.fixture()
async def session_factory():
    _prepare_tables()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def org_and_user(session_factory):
    async with session_factory() as s:
        org = Organization(name="Org", type="project_center", plan="free")
        s.add(org)
        await s.flush()
        user = User(org_id=org.id, email="u@example.com", role="project_center")
        s.add(user)
        await s.commit()
        return str(org.id), str(user.id)


@pytest.mark.asyncio
async def test_in_app_persister_writes_notification_row(session_factory, org_and_user):
    """In-app delivery persists a notifications row (channel=in_app, Req 20)."""
    org_id, user_id = org_and_user
    persister = ns.SqlAlchemyInAppPersister(session_factory)
    event = ns.NotificationEvent(org_id=org_id, title="Hot", body="too hot")
    recipient = ns.Recipient.build(user_id, [ns.Channel.IN_APP])

    await persister(event, recipient)

    async with session_factory() as s:
        rows = (await s.execute(select(Notification))).scalars().all()
    assert len(rows) == 1
    assert rows[0].channel == "in_app"
    assert rows[0].title == "Hot"
    assert rows[0].body == "too hot"
    assert str(rows[0].user_id) == user_id


@pytest.mark.asyncio
async def test_deliver_persists_in_app_when_enabled(session_factory, org_and_user):
    """deliver_to_recipient wires in-app persistence through the persister."""
    org_id, user_id = org_and_user
    persister = ns.SqlAlchemyInAppPersister(session_factory)
    rec = _Recorder()
    event = ns.NotificationEvent(org_id=org_id, title="Hot", body="too hot")
    recipient = ns.Recipient.build(
        user_id, [ns.Channel.EMAIL, ns.Channel.IN_APP], email="u@example.com"
    )

    report = await ns.deliver_to_recipient(
        event, recipient, rec.clients(), persist_in_app=persister
    )

    assert set(report.delivered) == {ns.Channel.EMAIL, ns.Channel.IN_APP}
    async with session_factory() as s:
        count = len((await s.execute(select(Notification))).scalars().all())
    assert count == 1


# ---------------------------------------------------------------------------
# process_event + run loop
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_process_event_delivers_to_all_recipients():
    rec = _Recorder()
    recipients = [
        ns.Recipient.build("u1", [ns.Channel.EMAIL], email="a@x.com"),
        ns.Recipient.build("u2", [ns.Channel.EMAIL], email="b@x.com"),
    ]
    delivered = await ns.process_event(_event(), recipients, rec.clients())
    assert delivered == 2
    assert {e for e, _, _ in rec.email} == {"a@x.com", "b@x.com"}


@pytest.mark.asyncio
async def test_run_delivers_one_event_then_stops():
    rec = _Recorder()
    stop_event = asyncio.Event()
    events = [_event()]

    async def source():
        if events:
            return events.pop()
        stop_event.set()
        return None

    async def load_recipients(event):
        return [ns.Recipient.build("u1", [ns.Channel.EMAIL], email="a@x.com")]

    await asyncio.wait_for(
        ns.run(source, load_recipients, rec.clients(), stop_event=stop_event),
        timeout=2.0,
    )
    assert rec.email == [("a@x.com", "High temp", "Sensor over 30C")]
