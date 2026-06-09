// Unit tests for the billing API client surface (Task 15.5, Req 16, 17).
// The shared apiClient is mocked so we assert on the request shape (path + body)
// each function sends and that it returns the parsed response body, without any
// real network call.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import { getPlans, postQuote, subscribe, requestRefund } from "./billingApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getPlans", () => {
  it("GETs /billing/plans and returns the body", async () => {
    const body = { free: {}, pro: {}, pricing_tiers: [] };
    apiClient.get.mockResolvedValue({ data: body });

    const result = await getPlans();

    expect(apiClient.get).toHaveBeenCalledWith("/billing/plans");
    expect(result).toBe(body);
  });
});

describe("postQuote", () => {
  it("POSTs /billing/quote with snake_case fields and returns the body", async () => {
    const body = { device_count: 25, billing_cycle: "monthly", unit_price: 79, total: 1975 };
    apiClient.post.mockResolvedValue({ data: body });

    const result = await postQuote({ deviceCount: 25, billingCycle: "monthly" });

    expect(apiClient.post).toHaveBeenCalledWith("/billing/quote", {
      device_count: 25,
      billing_cycle: "monthly",
    });
    expect(result).toBe(body);
  });
});

describe("subscribe", () => {
  it("POSTs /billing/subscribe with only device_count and billing_cycle by default", async () => {
    apiClient.post.mockResolvedValue({ data: { subscription_id: "s1" } });

    await subscribe({ deviceCount: 3, billingCycle: "yearly" });

    expect(apiClient.post).toHaveBeenCalledWith("/billing/subscribe", {
      device_count: 3,
      billing_cycle: "yearly",
    });
  });

  it("includes device_id and coupon when provided (per-device + coupon)", async () => {
    apiClient.post.mockResolvedValue({ data: {} });

    await subscribe({
      deviceCount: 1,
      billingCycle: "monthly",
      deviceId: "dev-1",
      coupon: "WELCOME10",
    });

    expect(apiClient.post).toHaveBeenCalledWith("/billing/subscribe", {
      device_count: 1,
      billing_cycle: "monthly",
      device_id: "dev-1",
      coupon: "WELCOME10",
    });
  });
});

describe("requestRefund", () => {
  it("POSTs /billing/refund with the payment id", async () => {
    apiClient.post.mockResolvedValue({ data: { status: "processed" } });

    const result = await requestRefund({ paymentId: "pay-1" });

    expect(apiClient.post).toHaveBeenCalledWith("/billing/refund", {
      payment_id: "pay-1",
    });
    expect(result).toEqual({ status: "processed" });
  });

  it("POSTs the subscription id when given instead", async () => {
    apiClient.post.mockResolvedValue({ data: {} });

    await requestRefund({ subscriptionId: "sub-1" });

    expect(apiClient.post).toHaveBeenCalledWith("/billing/refund", {
      subscription_id: "sub-1",
    });
  });
});
