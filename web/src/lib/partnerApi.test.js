// Unit tests for the partner wallet/payout API client surface
// (Task 16.6, Req 18.4, 18.5). The shared apiClient is mocked so we assert on
// the request shape (path + body) and that the parsed response body is
// returned, without any real network call.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import { getWallet, requestPayout } from "./partnerApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getWallet", () => {
  it("GETs /partner/wallet and returns the body", async () => {
    const body = {
      balance: "100",
      commissions: [
        {
          id: "c1",
          amount: "50",
          device_id: null,
          payment_id: null,
          period_month: "2025-01",
        },
      ],
    };
    apiClient.get.mockResolvedValue({ data: body });

    const result = await getWallet();

    expect(apiClient.get).toHaveBeenCalledWith("/partner/wallet");
    expect(result).toBe(body);
  });
});

describe("requestPayout", () => {
  it("POSTs /partner/payouts with amount + destination and returns the body", async () => {
    const body = { id: "p1", amount: "40", status: "PENDING" };
    apiClient.post.mockResolvedValue({ data: body });

    const result = await requestPayout({ amount: 40, destination: "upi:org@bank" });

    expect(apiClient.post).toHaveBeenCalledWith("/partner/payouts", {
      amount: 40,
      destination: "upi:org@bank",
    });
    expect(result).toBe(body);
  });

  it("omits destination when not provided", async () => {
    apiClient.post.mockResolvedValue({ data: { id: "p2", status: "PENDING" } });

    await requestPayout({ amount: 25 });

    expect(apiClient.post).toHaveBeenCalledWith("/partner/payouts", {
      amount: 25,
    });
  });
});
