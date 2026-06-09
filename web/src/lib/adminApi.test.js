// Unit tests for the Super_Admin platform API client (Task 20.7, Req 23-29).
// The shared apiClient is mocked so we assert on the request shape (method,
// path, body/params) and that the parsed response body is returned, without any
// real network call.

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import apiClient from "@/lib/apiClient";
import {
  getOverview,
  createCompany,
  suspendCompany,
  deleteCompany,
  resetUserPassword,
  changeUserRole,
  reassignDevice,
  getMqttNodes,
  registerMqttNode,
  deregisterMqttNode,
  getRevenue,
  getCoupons,
  createCoupon,
  deleteCoupon,
  setCommissionOverride,
  getReferrals,
  getSiteAnalytics,
  getNotificationSettings,
  updateNotificationSettings,
  getHealth,
  getErrors,
  getSecurity,
  getSettings,
  updateSettings,
} from "./adminApi.js";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("overview", () => {
  it("GETs /admin/overview and returns the body", async () => {
    const body = { companies: 3, devices: 9, users: 12, online: 4, revenue: "100" };
    apiClient.get.mockResolvedValue({ data: body });
    const result = await getOverview();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/overview");
    expect(result).toBe(body);
  });
});

describe("company management", () => {
  it("creates a company with name/plan/type", async () => {
    apiClient.post.mockResolvedValue({ data: { id: "1" } });
    await createCompany({ name: "Acme" });
    expect(apiClient.post).toHaveBeenCalledWith("/admin/companies", {
      name: "Acme",
      plan: "free",
      type: "project_center",
    });
  });

  it("suspends a company by id", async () => {
    apiClient.patch.mockResolvedValue({ data: {} });
    await suspendCompany("org-1");
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/companies/org-1/suspend");
  });

  it("deletes a company by id", async () => {
    apiClient.delete.mockResolvedValue({ data: null });
    await deleteCompany("org-1");
    expect(apiClient.delete).toHaveBeenCalledWith("/admin/companies/org-1");
  });
});

describe("user management", () => {
  it("resets a user password", async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    await resetUserPassword("u-1", "supersecret");
    expect(apiClient.post).toHaveBeenCalledWith("/admin/users/u-1/reset-password", {
      new_password: "supersecret",
    });
  });

  it("changes a user role", async () => {
    apiClient.patch.mockResolvedValue({ data: {} });
    await changeUserRole("u-1", "project_center");
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/users/u-1/role", {
      role: "project_center",
    });
  });

  it("reassigns a device across orgs", async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    await reassignDevice("d-1", "org-2");
    expect(apiClient.post).toHaveBeenCalledWith("/admin/devices/d-1/reassign", {
      org_id: "org-2",
    });
  });
});

describe("mqtt nodes", () => {
  it("lists nodes", async () => {
    const body = [{ id: "n-1" }];
    apiClient.get.mockResolvedValue({ data: body });
    const result = await getMqttNodes();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/mqtt-nodes");
    expect(result).toBe(body);
  });

  it("registers a node", async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    await registerMqttNode({ ip: "10.0.0.1", port: 1883, capacity: 1000 });
    expect(apiClient.post).toHaveBeenCalledWith("/admin/mqtt-nodes", {
      ip: "10.0.0.1",
      port: 1883,
      capacity: 1000,
    });
  });

  it("deregisters a node", async () => {
    apiClient.delete.mockResolvedValue({ data: null });
    await deregisterMqttNode("n-1");
    expect(apiClient.delete).toHaveBeenCalledWith("/admin/mqtt-nodes/n-1");
  });
});

describe("revenue", () => {
  it("GETs /admin/revenue", async () => {
    const body = { mrr: 100 };
    apiClient.get.mockResolvedValue({ data: body });
    const result = await getRevenue();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/revenue");
    expect(result).toBe(body);
  });
});

describe("coupons / commission / referrals", () => {
  it("lists coupons", async () => {
    apiClient.get.mockResolvedValue({ data: [] });
    await getCoupons();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/coupons");
  });

  it("creates a coupon mapping camelCase to snake_case", async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    await createCoupon({ code: "SAVE20", discountType: "percent", value: 20 });
    expect(apiClient.post).toHaveBeenCalledWith("/admin/coupons", {
      code: "SAVE20",
      discount_type: "percent",
      value: 20,
      max_redemptions: null,
      valid_until: null,
      active: true,
    });
  });

  it("deletes a coupon", async () => {
    apiClient.delete.mockResolvedValue({ data: null });
    await deleteCoupon("c-1");
    expect(apiClient.delete).toHaveBeenCalledWith("/admin/coupons/c-1");
  });

  it("sets a commission override (including null to clear)", async () => {
    apiClient.patch.mockResolvedValue({ data: {} });
    await setCommissionOverride("org-1", 0);
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/partners/org-1/commission", {
      rate: 0,
    });
    await setCommissionOverride("org-1", null);
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/partners/org-1/commission", {
      rate: null,
    });
  });

  it("lists referrals", async () => {
    apiClient.get.mockResolvedValue({ data: [] });
    await getReferrals();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/referrals");
  });
});

describe("content", () => {
  it("GETs site analytics", async () => {
    apiClient.get.mockResolvedValue({ data: {} });
    await getSiteAnalytics();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/site-analytics");
  });

  it("GETs notification settings", async () => {
    apiClient.get.mockResolvedValue({ data: {} });
    await getNotificationSettings();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/notification-settings");
  });

  it("PATCHes only provided notification channels", async () => {
    apiClient.patch.mockResolvedValue({ data: {} });
    await updateNotificationSettings({ telegram: { enabled: true } });
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/notification-settings", {
      telegram: { enabled: true },
    });
  });
});

describe("health / errors", () => {
  it("GETs health", async () => {
    apiClient.get.mockResolvedValue({ data: { services: [] } });
    await getHealth();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/health");
  });

  it("GETs errors with default params", async () => {
    apiClient.get.mockResolvedValue({ data: { recent: [], trends: [] } });
    await getErrors();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/errors", {
      params: { limit: 50, days: 7 },
    });
  });
});

describe("security / settings", () => {
  it("GETs security with default params", async () => {
    apiClient.get.mockResolvedValue({ data: {} });
    await getSecurity();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/security", {
      params: { limit: 50 },
    });
  });

  it("GETs settings", async () => {
    apiClient.get.mockResolvedValue({ data: { settings: {} } });
    await getSettings();
    expect(apiClient.get).toHaveBeenCalledWith("/admin/settings");
  });

  it("PATCHes settings wrapped in updates", async () => {
    apiClient.patch.mockResolvedValue({ data: { settings: {} } });
    await updateSettings({ jwt_expiry: 3600 });
    expect(apiClient.patch).toHaveBeenCalledWith("/admin/settings", {
      updates: { jwt_expiry: 3600 },
    });
  });
});
