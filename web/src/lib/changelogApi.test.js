// Unit tests for the changelog / "What's new" API client surface (Task 19.7,
// Req 22.1, 22.2). The shared apiClient is mocked so we assert on the request
// path and that the parsed body is returned/unwrapped.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import {
  listChangelog,
  getUnseenChangelog,
  markChangelogSeen,
} from "./changelogApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listChangelog", () => {
  it("GETs /changelog and unwraps { entries } (Req 22.1)", async () => {
    const entries = [{ id: "c1", title: "v1" }];
    apiClient.get.mockResolvedValue({ data: { entries } });

    const result = await listChangelog();

    expect(apiClient.get).toHaveBeenCalledWith("/changelog");
    expect(result).toBe(entries);
  });
});

describe("getUnseenChangelog", () => {
  it("GETs /changelog/unseen and returns { show_popup, entries } (Req 22.2)", async () => {
    const body = { show_popup: true, entries: [{ id: "c2" }] };
    apiClient.get.mockResolvedValue({ data: body });

    const result = await getUnseenChangelog();

    expect(apiClient.get).toHaveBeenCalledWith("/changelog/unseen");
    expect(result).toBe(body);
  });
});

describe("markChangelogSeen", () => {
  it("POSTs /changelog/seen and returns { last_seen_at } (Req 22.2)", async () => {
    const body = { last_seen_at: "2025-01-01T00:00:00Z" };
    apiClient.post.mockResolvedValue({ data: body });

    const result = await markChangelogSeen();

    expect(apiClient.post).toHaveBeenCalledWith("/changelog/seen");
    expect(result).toBe(body);
  });
});
