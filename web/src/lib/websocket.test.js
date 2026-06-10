// Unit tests for the WebSocket URL builder (Task 8.2, Req 7.4).
// buildWsUrl is pure, so it is exercised directly without a live socket.

import { describe, it, expect } from "vitest";
import { buildWsUrl } from "./websocket.js";

describe("buildWsUrl", () => {
  it("derives ws:// from an http origin and a relative API base", () => {
    const url = buildWsUrl("abc", {
      apiBase: "/api/v1",
      origin: "http://localhost:5173",
    });
    expect(url).toBe("ws://localhost:5173/ws?token=abc");
  });

  it("derives wss:// from an https origin", () => {
    const url = buildWsUrl("t", {
      apiBase: "/api/v1",
      origin: "https://app.iotaps.com",
    });
    expect(url).toBe("wss://app.iotaps.com/ws?token=t");
  });

  it("supports an absolute https API base", () => {
    const url = buildWsUrl("t", { apiBase: "https://api.iotaps.com/api/v1" });
    expect(url).toBe("wss://api.iotaps.com/ws?token=t");
  });

  it("omits the token query when no token is provided", () => {
    const url = buildWsUrl(null, {
      apiBase: "/api/v1",
      origin: "http://localhost",
    });
    expect(url).toBe("ws://localhost/ws");
  });

  it("url-encodes the token", () => {
    const url = buildWsUrl("a b&c", {
      apiBase: "/api/v1",
      origin: "http://localhost",
    });
    expect(url).toContain("token=a%20b%26c");
  });
});
