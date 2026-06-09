"""Tests for the WebSocket gateway (Task 5.5, Req 6.4, 7.4).

Exercises the gateway's pure mapping/auth helpers and the session bridge logic
against an in-memory ``fakeredis`` pub/sub - no live Redis or ASGI server. The
endpoint's auth rejection path is covered through the FastAPI ``TestClient``.

Covered behaviour:
  - client channel name -> Redis channel mapping (device/dashboard)
  - bearer-token extraction (query param + Authorization header)
  - JWT authentication of a connection (valid / missing / invalid)
  - subscribe/unsubscribe translation onto the Redis pub/sub connection
  - real-time bridging of every message-contract type to the client
  - unauthorized/unrecognized channels are skipped at subscribe time
  - endpoint rejects connections without a valid token (Req 1, 2)
"""

from __future__ import annotations

import asyncio
import json

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

import app.api.ws as ws_module
from app.api import ws as ws
from app.core import redis_keys as rk
from app.core.security import jwt as jwt_service
from app.core.security.principal import Principal
from app.main import create_app


# ---------------------------------------------------------------------------
# Test settings + token helpers
# ---------------------------------------------------------------------------
def _settings():
    from app.core.config import Settings

    return Settings(
        jwt_secret="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_ttl_seconds=900,
        jwt_refresh_token_ttl_seconds=3600,
    )


def _token(role: str = "project_center") -> str:
    return jwt_service.create_access_token(
        user_id="user-1", org_id="org-1", role=role, settings=_settings()
    )


# ---------------------------------------------------------------------------
# Channel mapping
# ---------------------------------------------------------------------------
def test_resolve_device_channel_maps_to_telemetry_and_device_channels():
    channels = ws.resolve_redis_channels("device:abc")
    assert channels == [rk.telemetry_channel("abc"), rk.device_channel("abc")]


def test_resolve_dashboard_channel_maps_to_dashboard_channel():
    assert ws.resolve_redis_channels("dashboard:42") == [rk.dashboard_channel("42")]


@pytest.mark.parametrize("name", ["", "device:", "dashboard:", "bogus", "device", "other:1"])
def test_resolve_unrecognized_channel_returns_empty(name):
    assert ws.resolve_redis_channels(name) == []
    assert ws.is_valid_client_channel(name) is False


# ---------------------------------------------------------------------------
# Token extraction + authentication
# ---------------------------------------------------------------------------
def test_extract_token_prefers_query_param():
    assert ws.extract_token("tok123", "Bearer header-tok") == "tok123"


def test_extract_token_from_authorization_header():
    assert ws.extract_token(None, "Bearer header-tok") == "header-tok"


def test_extract_token_missing_returns_none():
    assert ws.extract_token(None, None) is None
    assert ws.extract_token(None, "Basic xyz") is None


def test_authenticate_valid_token(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings)
    principal = ws.authenticate(_token())
    assert isinstance(principal, Principal)
    assert principal.org_id == "org-1"
    assert principal.role == "project_center"


def test_authenticate_missing_token_raises():
    with pytest.raises(jwt_service.TokenError):
        ws.authenticate(None)


def test_authenticate_invalid_token_raises(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings)
    with pytest.raises(jwt_service.TokenError):
        ws.authenticate("not-a-jwt")


# ---------------------------------------------------------------------------
# Session bridge: subscribe / unsubscribe / forward
# ---------------------------------------------------------------------------
class _FakeWebSocket:
    """Captures messages sent to the client."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


def _principal() -> Principal:
    return Principal(user_id="user-1", org_id="org-1", role="project_center")


async def _drain(redis, session, sink, *, expected: int, timeout: float = 2.0):
    """Run the pump until ``expected`` messages are forwarded (or timeout)."""
    pump = asyncio.create_task(session.pump())
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while len(sink.sent) < expected and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.01)
    finally:
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass


async def _subscribe_and_publish(client_channel, redis_channel, message):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    sink = _FakeWebSocket()
    session = ws.WebSocketSession(sink.send_text, _principal(), redis)
    await session.subscribe([client_channel])
    # Give the pubsub subscription a moment to register before publishing.
    pump = asyncio.create_task(session.pump())
    await asyncio.sleep(0.05)
    await redis.publish(redis_channel, message)
    deadline = asyncio.get_event_loop().time() + 2.0
    while not sink.sent and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    await session.close()
    return sink.sent


def test_subscribe_registers_redis_channels():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        session = ws.WebSocketSession(_FakeWebSocket().send_text, _principal(), redis)
        await session.subscribe(["device:d1", "dashboard:db1"])
        assert session.subscriptions["device:d1"] == [
            rk.telemetry_channel("d1"),
            rk.device_channel("d1"),
        ]
        assert session.subscriptions["dashboard:db1"] == [rk.dashboard_channel("db1")]
        await session.close()

    asyncio.run(_run())


def test_subscribe_skips_unrecognized_channels():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        session = ws.WebSocketSession(_FakeWebSocket().send_text, _principal(), redis)
        await session.subscribe(["bogus", "device:", "device:ok"])
        assert list(session.subscriptions) == ["device:ok"]
        await session.close()

    asyncio.run(_run())


def test_unsubscribe_removes_channel():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        session = ws.WebSocketSession(_FakeWebSocket().send_text, _principal(), redis)
        await session.subscribe(["device:d1"])
        await session.unsubscribe(["device:d1"])
        assert "device:d1" not in session.subscriptions
        await session.close()

    asyncio.run(_run())


def test_subscribe_respects_authorizer_denial():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

        async def deny_all(principal, channel):
            return False

        session = ws.WebSocketSession(
            _FakeWebSocket().send_text, _principal(), redis, authorizer=deny_all
        )
        await session.subscribe(["device:d1"])
        assert session.subscriptions == {}
        await session.close()

    asyncio.run(_run())


def test_bridge_forwards_telemetry_message():
    sent = asyncio.run(
        _subscribe_and_publish(
            "device:d1",
            rk.telemetry_channel("d1"),
            json.dumps({"type": "telemetry", "device_id": "d1", "ts": "t", "data": {"temp": 1}}),
        )
    )
    assert len(sent) == 1
    assert json.loads(sent[0])["type"] == "telemetry"


def test_bridge_forwards_command_status_on_device_channel():
    sent = asyncio.run(
        _subscribe_and_publish(
            "device:d1",
            rk.device_channel("d1"),
            json.dumps({"type": "command_status", "command_id": "c1", "status": "CONFIRMED"}),
        )
    )
    assert len(sent) == 1
    body = json.loads(sent[0])
    assert body["type"] == "command_status"
    assert body["status"] == "CONFIRMED"


def test_bridge_forwards_alert_message():
    sent = asyncio.run(
        _subscribe_and_publish(
            "device:d1",
            rk.device_channel("d1"),
            json.dumps({"type": "alert", "rule_id": "r1", "message": "high temp"}),
        )
    )
    assert len(sent) == 1
    assert json.loads(sent[0])["type"] == "alert"


def test_bridge_forwards_notification_on_dashboard_channel():
    sent = asyncio.run(
        _subscribe_and_publish(
            "dashboard:db1",
            rk.dashboard_channel("db1"),
            json.dumps({"type": "notification", "title": "Hi", "body": "There"}),
        )
    )
    assert len(sent) == 1
    assert json.loads(sent[0])["type"] == "notification"


def test_handle_message_ignores_malformed_frames():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        session = ws.WebSocketSession(_FakeWebSocket().send_text, _principal(), redis)
        # None of these should raise or create subscriptions.
        await session.handle_message("not json")
        await session.handle_message(json.dumps(["a", "list"]))
        await session.handle_message(json.dumps({"action": "subscribe"}))
        await session.handle_message(json.dumps({"action": "bogus", "channels": ["device:d1"]}))
        assert session.subscriptions == {}
        await session.close()

    asyncio.run(_run())


def test_handle_message_subscribe_then_unsubscribe():
    async def _run():
        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        session = ws.WebSocketSession(_FakeWebSocket().send_text, _principal(), redis)
        await session.handle_message(json.dumps({"action": "subscribe", "channels": ["device:d1"]}))
        assert "device:d1" in session.subscriptions
        await session.handle_message(
            json.dumps({"action": "unsubscribe", "channels": ["device:d1"]})
        )
        assert "device:d1" not in session.subscriptions
        await session.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Endpoint authentication (via TestClient)
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(jwt_service, "get_settings", _settings)
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ws_module, "get_redis", lambda: fake)
    return TestClient(create_app())


def test_endpoint_rejects_missing_token(client):
    from starlette.websockets import WebSocketDisconnect as StarletteWSDisconnect

    with pytest.raises(StarletteWSDisconnect) as exc:
        with client.websocket_connect("/ws"):
            pass
    assert exc.value.code == ws.WS_CLOSE_UNAUTHORIZED


def test_endpoint_rejects_invalid_token(client):
    from starlette.websockets import WebSocketDisconnect as StarletteWSDisconnect

    with pytest.raises(StarletteWSDisconnect) as exc:
        with client.websocket_connect("/ws?token=not-a-jwt"):
            pass
    assert exc.value.code == ws.WS_CLOSE_UNAUTHORIZED


def test_endpoint_accepts_valid_token_and_subscribes(client):
    with client.websocket_connect(f"/ws?token={_token()}") as conn:
        conn.send_text(json.dumps({"action": "subscribe", "channels": ["device:d1"]}))
        # No exception => handshake accepted and control frame processed.
        conn.send_text(json.dumps({"action": "unsubscribe", "channels": ["device:d1"]}))
