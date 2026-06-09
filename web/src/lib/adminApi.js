import apiClient from "@/lib/apiClient";

// Super_Admin platform API surface (design.md "Admin", Req 23-29). Each function
// maps 1:1 to a backend endpoint under /api/v1/admin and returns the parsed
// response body. Token handling is applied by the shared apiClient; every route
// is Super_Admin-only on the backend (require_role(ROLE_SUPER_ADMIN)).
//
// Backend routers:
//   admin.py          -> overview, companies, users, devices            (Req 23)
//   admin_nodes.py    -> mqtt-nodes                                     (Req 24)
//   admin_revenue.py  -> revenue                                        (Req 25)
//   admin_content.py  -> coupons, commission, referrals, templates,
//                        notification-settings, site-analytics          (Req 26, 27)
//   admin_ops.py      -> health, errors, security, settings, resources,
//                        backups, marketing                             (Req 28, 29)

// ---------------------------------------------------------------------------
// Overview (Req 23.1)
// ---------------------------------------------------------------------------
/** Platform-wide counts, online devices, revenue, and server health (Req 23.1). */
export async function getOverview() {
  const { data } = await apiClient.get("/admin/overview");
  return data; // { companies, devices, users, online, revenue, server_health }
}

// ---------------------------------------------------------------------------
// Company / user / device management (Req 23.2-23.6)
// ---------------------------------------------------------------------------
/** Create a new company Organization (Req 23.2). */
export async function createCompany({ name, plan = "free", type = "project_center" }) {
  const { data } = await apiClient.post("/admin/companies", { name, plan, type });
  return data; // CompanyOut
}

/** Suspend a company: deny its users new sign-ins (Req 23.2, 23.3). */
export async function suspendCompany(companyId) {
  const { data } = await apiClient.patch(`/admin/companies/${companyId}/suspend`);
  return data; // CompanyOut
}

/** Delete a company Organization (Req 23.2). */
export async function deleteCompany(companyId) {
  await apiClient.delete(`/admin/companies/${companyId}`);
}

/** Reset a user's password across any organization (Req 23.4). */
export async function resetUserPassword(userId, newPassword) {
  const { data } = await apiClient.post(`/admin/users/${userId}/reset-password`, {
    new_password: newPassword,
  });
  return data; // UserOut
}

/** Change a user's role and apply the corresponding permissions (Req 23.5). */
export async function changeUserRole(userId, role) {
  const { data } = await apiClient.patch(`/admin/users/${userId}/role`, { role });
  return data; // UserOut
}

/** Reassign a device to another Organization across org boundaries (Req 23.6). */
export async function reassignDevice(deviceId, orgId) {
  const { data } = await apiClient.post(`/admin/devices/${deviceId}/reassign`, {
    org_id: orgId,
  });
  return data; // DeviceOut
}

// ---------------------------------------------------------------------------
// MQTT nodes (Req 24.1-24.3)
// ---------------------------------------------------------------------------
/** List nodes with per-node RAM/CPU/disk + active connection metrics (Req 24.3). */
export async function getMqttNodes() {
  const { data } = await apiClient.get("/admin/mqtt-nodes");
  return data; // [MqttNodeOut]
}

/** Register an MQTT node, making it available for device assignment (Req 24.1). */
export async function registerMqttNode({ ip, port, capacity }) {
  const { data } = await apiClient.post("/admin/mqtt-nodes", { ip, port, capacity });
  return data; // MqttNodeOut
}

/** Deregister an MQTT node from device assignment (Req 24.2). */
export async function deregisterMqttNode(nodeId) {
  await apiClient.delete(`/admin/mqtt-nodes/${nodeId}`);
}

// ---------------------------------------------------------------------------
// Revenue analytics (Req 25.1, 25.2)
// ---------------------------------------------------------------------------
/** Platform revenue analytics: MRR, ARR, churn, funnel, ARPU, etc. (Req 25.1). */
export async function getRevenue() {
  const { data } = await apiClient.get("/admin/revenue");
  return data; // { mrr, arr, churn, funnel, arpu, by_source, top_orgs }
}

// ---------------------------------------------------------------------------
// Coupons / commission / referral (Req 26)
// ---------------------------------------------------------------------------
/** List all coupons, newest first (Req 26). */
export async function getCoupons() {
  const { data } = await apiClient.get("/admin/coupons");
  return data; // [CouponOut]
}

/** Create a discount coupon (Req 26). */
export async function createCoupon({
  code,
  discountType,
  value,
  maxRedemptions = null,
  validUntil = null,
  active = true,
}) {
  const { data } = await apiClient.post("/admin/coupons", {
    code,
    discount_type: discountType,
    value,
    max_redemptions: maxRedemptions,
    valid_until: validUntil,
    active,
  });
  return data; // CouponOut
}

/** Delete a coupon (Req 26). */
export async function deleteCoupon(couponId) {
  await apiClient.delete(`/admin/coupons/${couponId}`);
}

/** Set or clear a partner's commission override; null clears (Req 26.1, 26.2). */
export async function setCommissionOverride(orgId, rate) {
  const { data } = await apiClient.patch(`/admin/partners/${orgId}/commission`, {
    rate,
  });
  return data; // { org_id, commission_rate_override }
}

/** List referral records with fraud flags (Req 26.4). */
export async function getReferrals() {
  const { data } = await apiClient.get("/admin/referrals");
  return data; // [ReferralRecordOut]
}

// ---------------------------------------------------------------------------
// Content: templates, notification settings, site analytics (Req 27)
// ---------------------------------------------------------------------------
/** Return site analytics: page views, visitors, sessions (Req 27.1). */
export async function getSiteAnalytics() {
  const { data } = await apiClient.get("/admin/site-analytics");
  return data;
}

/** Return Telegram/push/email notification settings (Req 27.3). */
export async function getNotificationSettings() {
  const { data } = await apiClient.get("/admin/notification-settings");
  return data; // { telegram, push, email }
}

/** Apply Telegram/push/email notification settings platform-wide (Req 27.3). */
export async function updateNotificationSettings({ telegram, push, email } = {}) {
  const body = {};
  if (telegram !== undefined) body.telegram = telegram;
  if (push !== undefined) body.push = push;
  if (email !== undefined) body.email = email;
  const { data } = await apiClient.patch("/admin/notification-settings", body);
  return data;
}

// ---------------------------------------------------------------------------
// Health / errors (Req 28.1, 28.3)
// ---------------------------------------------------------------------------
/** Return the status of each platform service (Req 28.1). */
export async function getHealth() {
  const { data } = await apiClient.get("/admin/health");
  return data; // { services: [{ name, status }] }
}

/** Return recent errors and error trends over time (Req 28.3). */
export async function getErrors({ limit = 50, days = 7 } = {}) {
  const { data } = await apiClient.get("/admin/errors", { params: { limit, days } });
  return data; // { recent, trends }
}

// ---------------------------------------------------------------------------
// Security / settings (Req 29.2, 29.4)
// ---------------------------------------------------------------------------
/** Return login attempts, blocked IPs, and the audit log (Req 29.2). */
export async function getSecurity({ limit = 50 } = {}) {
  const { data } = await apiClient.get("/admin/security", { params: { limit } });
  return data; // { login_attempts, blocked_ips, audit_log }
}

/** Return all current platform settings (Req 29.4). */
export async function getSettings() {
  const { data } = await apiClient.get("/admin/settings");
  return data; // { settings }
}

/** Apply platform settings platform-wide immediately (Req 29.4). */
export async function updateSettings(updates) {
  const { data } = await apiClient.patch("/admin/settings", { updates });
  return data; // { settings }
}
