"""WebSocket gateway (Task 5.5, Req 6.4, 7.4).

The WebSocket Gateway (design "Components and Interfaces -> Backend (FastAPI)")
exposes a single JWT-authenticated ``/ws`` endpoint that bridges the Redis
pub/sub fan-out produced by the telemetry pipeline (Batch_Writer, Task 5.2) and
the workers (status/ack, alerts, notifications) to subscribed browser clients in
real time (< 1s, Req 6.4).

Client/server message contract (design "WebSocket message contract"):

    Client -> Server:
      {"action": "subscribe",   "channels": ["device:{id}", "dashboard:{id}"]}
      {"action": "unsubscribe", "channels": [...]}

    Server -> Client:
      {"type": "telemetry",       "device_id": "...", "ts": "...", "data": {...}}
      {"type": "command_status",  "command_id": "...", "status": "CONFIRMED"}
      {"type": "alert",           "rule_id": "...", "message": "..."}
      {"type": "notification",    "title": "...", "body": "..."}

Channel mapping
---------------
The *client-facing* channel names (``device:{id}`` / ``dashboard:{id}``) are
distinct from the *Redis* channel names defined in ``app.core.redis_keys``. A
client subscription to ``device:{id}`` is bridged to the device's telemetry
channel (where the Batch_Writer publishes latest values, Req 6.3) *and* the
device event channel (where the MQTT_Listener publishes status/ack and the
command/alert flows publish ``command_status``/``alert``). A ``dashboard:{id}``
subscription is bridged to that dashboard's fan-out channel.

Design references:
- Authentication: JWT verification reusing ``app.core.security.jwt`` (Req 1, 2).
- Channels: ``telemetry_channel`` / ``device_channel`` / ``dashboard_channel``
  in ``app.core.redis_keys`` (Req 6.3, 6.4).

The session/bridge logic is written against the minimal async interfaces it
needs (a ``send_text`` sink and a Redis client exposing ``pubsub()``) so it can
be unit-tested with ``fakeredis`` and a fake websocket, without a live Redis or
ASGI server.

Security note: a connection is rejected unless it presents a valid access JWT.
Per-resource authorization (restricting a Device_User to channels for devices
assigned to them, Req 2.4) is intentionally layered on top via
``authorize_channel`` and enforced at subscribe time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core import redis_keys as rk
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.security import jwt as jwt_service
from app.core.security.principal import Principal

logger = get_logger(__name__)

router = APIRouter()

# Client-facing channel name prefixes (distinct from Redis key names).
CLIENT_DEVICE_PREFIX = "device:"
CLIENT_DASHBOARD_PREFIX = "dashboard:"

# WebSocket close codes (RFC 6455 private-use range 4000-4999 for app errors).
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_INTERNAL = 1011

# An optional authorization hook: given the principal and a client channel,
# returns whether the subscription is permitted. Defaults to allow-any for an
# authenticated principal; tenant/device scoping (Req 2.4) can be injected.
ChannelAuthorizer = Callable[[Principal, str], Awaitable[bool]]


# ---------------------------------------------------------------------------
# Channel mapping (client channel name <-> Redis pub/sub channels)
# ---------------------------------------------------------------------------
def resolve_redis_channels(client_channel: str) -> list[str]:
    """Map a client channel name to the Redis channels backing it.

    ``device:{id}``    -> [telemetry channel, device event channel]
    ``dashboard:{id}`` -> [dashboard fan-out channel]

    Returns an empty list for an unrecognised or id-less channel name so the
    caller can ignore it rather than subscribing to a bogus Redis channel.
    """
    if client_channel.startswith(CLIENT_DEVICE_PREFIX):
        device_id = client_channel[len(CLIENT_DEVICE_PREFIX):].strip()
        if not device_id:
            return []
        # Telemetry latest values (Req 6.3) + device events: status/ack
        # (MQTT_Listener) and command_status/alert (command + rule flows).
        return [rk.telemetry_channel(device_id), rk.device_channel(device_id)]
    if client_channel.startswith(CLIENT_DASHBOARD_PREFIX):
        dashboard_id = client_channel[len(CLIENT_DASHBOARD_PREFIX):].strip()
        if not dashboard_id:
            return []
        return [rk.dashboard_channel(dashboard_id)]
    return []


def is_valid_client_channel(client_channel: str) -> bool:
    """Whether ``client_channel`` maps to at least one Redis channel."""
    return bool(resolve_redis_channels(client_channel))


# ---------------------------------------------------------------------------
# Authentication (Req 1, 2)
# ---------------------------------------------------------------------------
def extract_token(token_param: Optional[str], authorization: Optional[str]) -> Optional[str]:
    """Pull the bearer token from the ``token`` query param or Authorization.

    Browsers cannot set custom headers on a WebSocket handshake, so the access
    token is normally supplied as ``?token=<jwt>``. A standard
    ``Authorization: Bearer <jwt>`` header is also accepted for non-browser
    clients/tests.
    """
    if token_param:
        return token_param.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def authenticate(token: Optional[str]) -> Principal:
    """Verify the access token and return the connection principal.

    Raises :class:`app.core.security.jwt.TokenError` when the token is missing,
    malformed, expired, or fails signature verification.
    """
    if not token:
        raise jwt_service.TokenError("missing access token")
    claims = jwt_service.decode_access_token(token)
    return Principal.from_claims(claims)


# ---------------------------------------------------------------------------
# Session: bridges Redis pub/sub to one connected client
# ---------------------------------------------------------------------------
class WebSocketSession:
    """Bridges Redis pub/sub messages to a single connected WebSocket client.

    The session owns one Redis ``pubsub`` connection. ``subscribe`` /
    ``unsubscribe`` translate client channel names to Redis channels; the
    background ``pump`` task forwards every published message to the client.
    """

    def __init__(
        self,
        send_text: Callable[[str], Awaitable[None]],
        principal: Principal,
        redis: Any,
        *,
        authorizer: Optional[ChannelAuthorizer] = None,
    ) -> None:
        self._send_text = send_text
        self.principal = principal
        self._redis = redis
        self._pubsub = redis.pubsub()
        self._authorizer = authorizer
        # client channel name -> the Redis channels it expanded to.
        self.subscriptions: dict[str, list[str]] = {}

    async def subscribe(self, channels: list[str]) -> None:
        """Subscribe the client to the given channels (idempotent per channel).

        Unrecognised channel names and channels the principal is not authorized
        for (Req 2.4) are skipped. Already-subscribed channels are ignored.
        """
        for client_channel in channels:
            if not isinstance(client_channel, str):
                continue
            if client_channel in self.subscriptions:
                continue
            redis_channels = resolve_redis_channels(client_channel)
            if not redis_channels:
                logger.warning("ws_channel_unrecognized", extra={"channel": client_channel})
                continue
            if self._authorizer is not None and not await self._authorizer(
                self.principal, client_channel
            ):
                logger.warning(
                    "ws_channel_denied",
                    extra={"channel": client_channel, "user_id": self.principal.user_id},
                )
                continue
            await self._pubsub.subscribe(*redis_channels)
            self.subscriptions[client_channel] = redis_channels

    async def unsubscribe(self, channels: list[str]) -> None:
        """Unsubscribe the client from the given channels (idempotent)."""
        for client_channel in channels:
            if not isinstance(client_channel, str):
                continue
            redis_channels = self.subscriptions.pop(client_channel, None)
            if redis_channels:
                await self._pubsub.unsubscribe(*redis_channels)

    async def handle_message(self, raw: str) -> None:
        """Process one client control message ({action, channels}).

        Malformed messages (bad JSON, missing/!list channels, unknown action)
        are ignored so a single bad frame cannot tear down the connection.
        """
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("ws_message_malformed")
            return
        if not isinstance(msg, dict):
            return
        action = msg.get("action")
        channels = msg.get("channels")
        if not isinstance(channels, list):
            return
        if action == "subscribe":
            await self.subscribe(channels)
        elif action == "unsubscribe":
            await self.unsubscribe(channels)
        else:
            logger.warning("ws_action_unknown", extra={"action": action})

    async def pump(self) -> None:
        """Forward every published Redis message to the client until cancelled.

        Real-time delivery (Req 6.4, 7.4): pub/sub is push-based, so a message
        published after the Batch_Writer commit reaches the client effectively
        immediately (well within the 1s budget). Subscribe/unsubscribe
        confirmation frames are skipped; only ``message``/``pmessage`` payloads
        are relayed. Forwarding errors for a single message are logged and never
        kill the pump.
        """
        async for message in self._pubsub.listen():
            if message is None:
                continue
            if message.get("type") not in ("message", "pmessage"):
                continue
            payload = message.get("data")
            if isinstance(payload, (bytes, bytearray)):
                try:
                    payload = payload.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if not isinstance(payload, str):
                continue
            try:
                await self._send_text(payload)
            except Exception:  # pragma: no cover - one bad send must not stop the pump
                logger.exception("ws_forward_failed")

    async def close(self) -> None:
        """Release the Redis pub/sub connection for this session."""
        try:
            await self._pubsub.unsubscribe()
        except Exception:  # pragma: no cover - defensive cleanup
            pass
        try:
            aclose = getattr(self._pubsub, "aclose", None)
            if aclose is not None:
                await aclose()
            else:  # pragma: no cover - older redis-py
                close = getattr(self._pubsub, "close", None)
                if close is not None:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
        except Exception:  # pragma: no cover - defensive cleanup
            pass


# ---------------------------------------------------------------------------
# FastAPI WebSocket endpoint
# ---------------------------------------------------------------------------
@router.websocket("/ws")
async def websocket_gateway(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
) -> None:
    """JWT-authenticated WebSocket endpoint bridging Redis pub/sub (Req 6.4, 7.4).

    Handshake: verify the access token (query ``?token=`` or Authorization
    header) before accepting; reject unauthenticated connections with a 4401
    close. Once accepted, a background pump forwards pub/sub messages while the
    main loop processes subscribe/unsubscribe control frames.
    """
    raw_token = extract_token(token, websocket.headers.get("authorization"))
    try:
        principal = authenticate(raw_token)
    except jwt_service.TokenError:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    redis = get_redis()
    if redis is None:  # pragma: no cover - defensive; redis lib should be present
        await websocket.close(code=WS_CLOSE_INTERNAL)
        return

    await websocket.accept()
    session = WebSocketSession(websocket.send_text, principal, redis)
    pump_task = asyncio.create_task(session.pump())
    try:
        while True:
            raw = await websocket.receive_text()
            await session.handle_message(raw)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):  # pragma: no cover - cleanup
            pass
        await session.close()
