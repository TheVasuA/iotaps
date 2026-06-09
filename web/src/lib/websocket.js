import { tokenStore, API_BASE_URL } from "@/lib/apiClient";

// Single per-session WebSocket connection to the backend gateway (/ws), per
// design.md: "The SPA maintains one WebSocket connection per session, subscribes
// to device/dashboard channels, and dispatches incoming telemetry into Redux."
//
// Message contract (design "WebSocket message contract"):
//   Client -> Server: {action: "subscribe"|"unsubscribe", channels: [...]}
//   Server -> Client: {type: "telemetry"|"command_status"|"alert"|"notification", ...}
//
// This manager owns reconnection with backoff, re-subscribes the active channel
// set on reconnect, and fans incoming messages out to registered handlers.
// Browsers cannot set headers on the WS handshake, so the JWT is passed as
// ?token= (the gateway also accepts an Authorization header for non-browsers).

/** Resolve the ws(s):// URL for the gateway from the API base + access token. */
export function buildWsUrl(token, { apiBase = API_BASE_URL, origin } = {}) {
  // /api/v1 -> the gateway lives at /ws (sibling of the REST mount).
  const loc =
    origin ||
    (typeof window !== "undefined" && window.location
      ? window.location.origin
      : "http://localhost");
  let base;
  if (/^https?:\/\//i.test(apiBase)) {
    base = new URL(apiBase);
  } else {
    base = new URL(apiBase, loc);
  }
  const proto = base.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${base.host}/ws`;
  return token ? `${url}?token=${encodeURIComponent(token)}` : url;
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

class WebSocketManager {
  constructor() {
    this._ws = null;
    this._channels = new Set(); // desired subscriptions (client channel names)
    this._handlers = new Set(); // (message) => void
    this._statusHandlers = new Set(); // (status) => void
    this._attempts = 0;
    this._reconnectTimer = null;
    this._closedByUs = false;
    this._status = "closed"; // closed | connecting | open
    // Allow tests/SSR to inject a WebSocket implementation.
    this._WebSocketImpl =
      typeof WebSocket !== "undefined" ? WebSocket : undefined;
  }

  get status() {
    return this._status;
  }

  /** Open the connection (idempotent). Safe to call when already connected. */
  connect() {
    if (!this._WebSocketImpl) return; // no WS available (SSR / unsupported)
    if (this._ws && (this._status === "open" || this._status === "connecting")) {
      return;
    }
    this._closedByUs = false;
    const token = tokenStore.getAccess();
    const url = buildWsUrl(token);
    this._setStatus("connecting");
    let ws;
    try {
      ws = new this._WebSocketImpl(url);
    } catch {
      this._scheduleReconnect();
      return;
    }
    this._ws = ws;

    ws.onopen = () => {
      this._attempts = 0;
      this._setStatus("open");
      // Re-subscribe the full desired channel set on (re)connect.
      if (this._channels.size > 0) {
        this._send({ action: "subscribe", channels: [...this._channels] });
      }
    };
    ws.onmessage = (event) => this._onMessage(event.data);
    ws.onclose = () => {
      this._ws = null;
      this._setStatus("closed");
      if (!this._closedByUs) this._scheduleReconnect();
    };
    ws.onerror = () => {
      // onclose follows; reconnection is handled there.
      try {
        ws.close();
      } catch {
        /* noop */
      }
    };
  }

  /** Close the connection and cancel reconnection. Keeps desired channels. */
  disconnect() {
    this._closedByUs = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._ws) {
      try {
        this._ws.close();
      } catch {
        /* noop */
      }
      this._ws = null;
    }
    this._setStatus("closed");
  }

  /** Add the given channels to the subscription set and send if connected. */
  subscribe(channels) {
    const added = [];
    for (const c of channels) {
      if (!this._channels.has(c)) {
        this._channels.add(c);
        added.push(c);
      }
    }
    if (added.length && this._status === "open") {
      this._send({ action: "subscribe", channels: added });
    }
  }

  /** Remove the given channels from the subscription set and send if connected. */
  unsubscribe(channels) {
    const removed = [];
    for (const c of channels) {
      if (this._channels.has(c)) {
        this._channels.delete(c);
        removed.push(c);
      }
    }
    if (removed.length && this._status === "open") {
      this._send({ action: "unsubscribe", channels: removed });
    }
  }

  /** Register a message handler. Returns an unsubscribe function. */
  onMessage(handler) {
    this._handlers.add(handler);
    return () => this._handlers.delete(handler);
  }

  /** Register a connection-status handler. Returns an unsubscribe function. */
  onStatus(handler) {
    this._statusHandlers.add(handler);
    handler(this._status);
    return () => this._statusHandlers.delete(handler);
  }

  _setStatus(status) {
    this._status = status;
    for (const h of this._statusHandlers) {
      try {
        h(status);
      } catch {
        /* a bad status handler must not break others */
      }
    }
  }

  _send(obj) {
    if (this._ws && this._status === "open") {
      try {
        this._ws.send(JSON.stringify(obj));
      } catch {
        /* dropped frame; re-sent on reconnect */
      }
    }
  }

  _onMessage(raw) {
    let msg;
    try {
      msg = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch {
      return; // ignore malformed frames
    }
    if (!msg || typeof msg !== "object") return;
    for (const h of this._handlers) {
      try {
        h(msg);
      } catch {
        /* one bad handler must not break the others */
      }
    }
  }

  _scheduleReconnect() {
    if (this._closedByUs || this._reconnectTimer) return;
    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this._attempts,
      RECONNECT_MAX_MS
    );
    this._attempts += 1;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, delay);
  }
}

// One shared manager for the whole SPA (one connection per session).
export const wsManager = new WebSocketManager();

export { WebSocketManager };
export default wsManager;
