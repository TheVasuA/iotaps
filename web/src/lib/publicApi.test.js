// Unit tests for the public (unauthenticated) website API client (Task 21.1,
// Req 31.1, 31.4). We mock axios.create so we can assert the request paths and
// that responses are unwrapped, and confirm a bare axios instance is used (not
// the shared apiClient) so the public site never mutates auth token storage.

import { describe, it, expect, vi, beforeEach } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("axios", () => ({
  default: {
    create: vi.fn(() => ({ get: getMock })),
  },
}));

// apiClient exports API_BASE_URL, which publicApi imports.
vi.mock("@/lib/apiClient", () => ({
  API_BASE_URL: "/api/v1",
}));

import { getServiceStatus, getPublicChangelog } from "./publicApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getServiceStatus", () => {
  it("GETs /health and returns the status body (Req 31.4)", async () => {
    const body = {
      status: "ok",
      service: "iotaps-api",
      dependencies: [{ name: "redis", status: "ok" }],
    };
    getMock.mockResolvedValue({ data: body });

    const result = await getServiceStatus();

    expect(getMock).toHaveBeenCalledWith("/health");
    expect(result).toBe(body);
  });
});

describe("getPublicChangelog", () => {
  it("GETs /changelog and unwraps { entries } (Req 31.1)", async () => {
    const entries = [{ id: "c1", title: "v1.0" }];
    getMock.mockResolvedValue({ data: { entries } });

    const result = await getPublicChangelog();

    expect(getMock).toHaveBeenCalledWith("/changelog");
    expect(result).toBe(entries);
  });

  it("returns an empty array when no entries envelope is present", async () => {
    getMock.mockResolvedValue({ data: {} });

    const result = await getPublicChangelog();

    expect(result).toEqual([]);
  });
});
