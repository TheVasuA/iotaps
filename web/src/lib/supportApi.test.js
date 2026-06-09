// Unit tests for the support chat API client surface (Task 19.7, Req 21.1,
// 21.2, 21.3). The shared apiClient is mocked so we assert on the request shape
// (path + body) and that the parsed response body is returned.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import {
  listSupportMessages,
  sendSupportMessage,
  replySupportMessage,
} from "./supportApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listSupportMessages", () => {
  it("GETs /support/messages with no params and returns the body", async () => {
    const body = [{ id: "m1", message: "hi" }];
    apiClient.get.mockResolvedValue({ data: body });

    const result = await listSupportMessages();

    expect(apiClient.get).toHaveBeenCalledWith("/support/messages", {
      params: {},
    });
    expect(result).toBe(body);
  });

  it("passes device_id when filtering a thread (Req 21.1)", async () => {
    apiClient.get.mockResolvedValue({ data: [] });

    await listSupportMessages({ deviceId: "dev-1" });

    expect(apiClient.get).toHaveBeenCalledWith("/support/messages", {
      params: { device_id: "dev-1" },
    });
  });
});

describe("sendSupportMessage", () => {
  it("POSTs device_id + message and unwraps { message } (Req 21.1, 21.2)", async () => {
    const created = { id: "m2", device_id: "dev-1", message: "help" };
    apiClient.post.mockResolvedValue({ data: { message: created } });

    const result = await sendSupportMessage({
      deviceId: "dev-1",
      message: "help",
    });

    expect(apiClient.post).toHaveBeenCalledWith("/support/messages", {
      device_id: "dev-1",
      message: "help",
    });
    expect(result).toBe(created);
  });
});

describe("replySupportMessage", () => {
  it("POSTs to the reply endpoint and unwraps { message } (Req 21.3)", async () => {
    const created = { id: "m3", message: "on it" };
    apiClient.post.mockResolvedValue({ data: { message: created } });

    const result = await replySupportMessage("m2", "on it");

    expect(apiClient.post).toHaveBeenCalledWith("/support/messages/m2/reply", {
      message: "on it",
    });
    expect(result).toBe(created);
  });
});
