import { tokenStore } from "@/lib/apiClient";

// Minimal WebSocket client for the live-update gateway (design "WebSocket
// message contract", Req 6.4, 7.4). The SPA maintains one connection per
// session, subscribes to device/dashboard channels, and routes incoming
// messages (telemetry, command_status, alert, notification) to listeners.
//
// This is intentionally framework-agnostic: components subscribe to a channel
// and register a message handler, and the client manages the single underlying
// socket, (re)subscription, and reconnection with backoff. Command feedback
// (Task 9.3) uses it to receive command_status updates (Req 9.4, 9.7).

const WS_PATH = "/ws";

// Resolve the gateway URL. In dev, Vite proxies /ws to the backend; in prod
// Nginx terminates it. The JWT is passed as ?token= because browsers cannot set
// headers on the WebSocket handshake (see app/api/ws.py extract_token).
function resolveWsUrl() {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) return explicit;
  if (typeof window === "undefined") return WS_PATH;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${WS_PATH}`;
}

class RealtimeClient {
  constructor() {
    this._socket = null;
    this._connected = false;
    // client channel -> Set<handler>
    this._handlers = new Map();
    this._backoffMs = 1000;
    this._reconnectTimer = null;
    this._intentionalClose = false;
  }

  _send(obj) {
    if (this._socket && this._socket.readyState === WebSocket.OPEN) {
      this._socket.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }

  _openSocket() {
    if (this._socket) return;
    const token = tokenStore.getAccess();
    // Without a token the gateway rejects the handshake (4401); skip connecting
    // until the user is authenticated.
    if (!token) return;

    const url = `${resolveWsUrl()}?token=${encodeURIComponent(token)}`;
    let socket;
    try {
      socket = new WebSocket(url);
    } catch {
      this._scheduleReconnect();
      return;
    }
    this._socket = socket;
    this._intentionalClose = false;

    socket.onopen = () => {
      this._connected = true;
      this._backoffMs = 1000;
      // Re-subscribe to every channel that has live listeners.
      const channels = [...this._handlers.keys()];
      if (channels.length) this._send({ action: "subscribe", channels });
    };

    socket.onmessage = (event) => {
      this._dispatch(event.data);
    };

    socket.onclose = () => {
      this._connected = false;
      this._socket = null;
      if (!this._intentionalClose) this._scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose follows; reconnection is handled there.
      try {
        socket.close();
      } catch {
        /* noop */
      }
    };
  }

  _scheduleReconnect() {
    if (this._reconnectTimer || this._intentionalClose) return;
    if (this._handlers.size === 0) return; // nothing to reconnect for
    const delay = this._backoffMs;
    this._backoffMs = Math.min(this._backoffMs * 2, 30000);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this._openSocket();
    }, delay);
  }

  _dispatch(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return; // ignore malformed frames
    }
    if (!msg || typeof msg !== "object") return;
    // Fan a message out to every channel handler. The gateway multiplexes all
    // of a session's subscriptions over one socket and does not echo the client
    // channel name, so each handler decides whether the message concerns it
    // (e.g. command_status by command_id, telemetry by device_id).
    for (const handlers of this._handlers.values()) {
      for (const handler of handlers) {
        try {
          handler(msg);
        } catch {
          /* a bad handler must not break delivery to others */
        }
      }
    }
  }

  /**
   * Subscribe to a client channel ("device:{id}" / "dashboard:{id}") and
   * register a handler for messages. Returns an unsubscribe function that
   * removes the handler and, when a channel has no listeners left, tells the
   * gateway to stop forwarding it.
   */
  subscribe(channel, handler) {
    let handlers = this._handlers.get(channel);
    const isNewChannel = !handlers;
    if (!handlers) {
      handlers = new Set();
      this._handlers.set(channel, handlers);
    }
    handlers.add(handler);

    this._openSocket();
    if (isNewChannel && this._connected) {
      this._send({ action: "subscribe", channels: [channel] });
    }

    return () => this._removeHandler(channel, handler);
  }

  _removeHandler(channel, handler) {
    const handlers = this._handlers.get(channel);
    if (!handlers) return;
    handlers.delete(handler);
    if (handlers.size === 0) {
      this._handlers.delete(channel);
      this._send({ action: "unsubscribe", channels: [channel] });
    }
    // Close the socket entirely when nothing is listening anymore.
    if (this._handlers.size === 0) this.close();
  }

  close() {
    this._intentionalClose = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._socket) {
      try {
        this._socket.close();
      } catch {
        /* noop */
      }
      this._socket = null;
    }
    this._connected = false;
  }
}

// One shared client per SPA session.
const realtimeClient = new RealtimeClient();

export default realtimeClient;
