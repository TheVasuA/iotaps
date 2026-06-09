// Unit tests for the referrals API client surface (Task 17.3, Req 19.1, 19.2).
// The shared apiClient is mocked so we assert on the request shape (path) and
// that the parsed response body is returned, without any real network call.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import { getReferralSummary } from "./referralsApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getReferralSummary", () => {
  it("GETs /referrals and returns the body", async () => {
    const body = {
      code: "ABCD1234",
      count: 2,
      rewards: [
        {
          devices_granted: 2,
          months_granted: 1,
          granted_at: "2025-01-01T00:00:00Z",
          expires_at: "2025-01-31T00:00:00Z",
        },
      ],
    };
    apiClient.get.mockResolvedValue({ data: body });

    const result = await getReferralSummary();

    expect(apiClient.get).toHaveBeenCalledWith("/referrals");
    expect(result).toBe(body);
  });
});
