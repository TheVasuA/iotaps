// Unit tests for the public (unauthenticated) website API client (Task 21.1,
// Req 31.1, 31.4, 16.1). We mock axios.create so we can assert the request
// paths and that responses are unwrapped/normalised, and confirm a bare axios
// instance is used (not the shared apiClient) so the public site never mutates
// auth token storage.

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

import {
  getServiceStatus,
  getPublicChangelog,
  getPublicPlans,
  normalizePlans,
} from "./publicApi.js";

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

describe("normalizePlans", () => {
  const body = {
    free: { plan: "Free_Plan", max_devices: 2 },
    pro: { plan: "Pro_Plan", unit_price_monthly: 99, annual_unit_price: 948 },
    pricing_tiers: [
      { min_devices: 1, max_devices: 10, unit_price_monthly: 99 },
      { min_devices: 201, max_devices: null, unit_price_monthly: 59 },
    ],
  };

  it("maps snake_case tiers and the annual price to the display shape", () => {
    expect(normalizePlans(body)).toEqual({
      annualUnitPrice: 948,
      tiers: [
        { minDevices: 1, maxDevices: 10, unitPriceMonthly: 99 },
        { minDevices: 201, maxDevices: null, unitPriceMonthly: 59 },
      ],
    });
  });

  it("returns null on unusable bodies so callers can fall back", () => {
    expect(normalizePlans(null)).toBeNull();
    expect(normalizePlans({})).toBeNull();
    expect(
      normalizePlans({ pro: { annual_unit_price: 948 }, pricing_tiers: [] })
    ).toBeNull();
    // Missing annual price.
    expect(
      normalizePlans({ pro: {}, pricing_tiers: body.pricing_tiers })
    ).toBeNull();
    // Missing tier rates.
    expect(
      normalizePlans({
        pro: { annual_unit_price: 948 },
        pricing_tiers: [{ min_devices: 1, max_devices: 10 }],
      })
    ).toBeNull();
  });
});

describe("getPublicPlans", () => {
  it("GETs /billing/plans and returns the normalised display shape", async () => {
    getMock.mockResolvedValue({
      data: {
        pro: { annual_unit_price: 948 },
        pricing_tiers: [{ min_devices: 1, max_devices: 10, unit_price_monthly: 99 }],
      },
    });

    const result = await getPublicPlans();

    expect(getMock).toHaveBeenCalledWith("/billing/plans");
    expect(result).toEqual({
      annualUnitPrice: 948,
      tiers: [{ minDevices: 1, maxDevices: 10, unitPriceMonthly: 99 }],
    });
  });
});
