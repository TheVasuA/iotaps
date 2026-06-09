import apiClient from "@/lib/apiClient";

// Billing & subscription API surface (design.md "Billing, Partner, Referral",
// Req 16, 17). Each function maps 1:1 to a backend endpoint under
// /api/v1/billing and returns the parsed body. Token handling and tenant
// scoping are applied by the shared apiClient and the backend middleware.
//
// The pricing math also lives client-side in src/lib/pricing.js (the volume
// discount mirror, Task 14.5); the quote calculator uses that for an instant,
// offline preview and POST /billing/quote to confirm against the server.

/**
 * Fetch the Free/Pro plan entitlements and the monthly volume-discount tiers
 * (Req 16.1-16.5). Returns { free, pro, pricing_tiers }.
 */
export async function getPlans() {
  const { data } = await apiClient.get("/billing/plans");
  return data; // { free, pro, pricing_tiers }
}

/**
 * Quote a purchase server-side: resolve the volume-tier unit price and total
 * (Req 16.2-16.7).
 *
 * @param {{ deviceCount: number, billingCycle: "monthly"|"yearly" }} input
 * @returns {Promise<{device_count, billing_cycle, unit_price, total}>}
 */
export async function postQuote({ deviceCount, billingCycle }) {
  const { data } = await apiClient.post("/billing/quote", {
    device_count: deviceCount,
    billing_cycle: billingCycle,
  });
  return data;
}

/**
 * Start checkout: create a Razorpay order for a per-device or fleet Pro_Plan
 * purchase, with an optional coupon (Req 17.1, 17.4). Activation happens later
 * when Razorpay confirms capture via the webhook (Req 17.2), so the returned
 * order is "created" and not yet active.
 *
 * @param {{
 *   deviceCount: number,
 *   billingCycle: "monthly"|"yearly",
 *   deviceId?: string,
 *   coupon?: string
 * }} input
 * @returns {Promise<{
 *   subscription_id, razorpay_order, device_count, billing_cycle,
 *   unit_price, gross_total, amount_due, coupon_applied
 * }>}
 */
export async function subscribe({ deviceCount, billingCycle, deviceId, coupon }) {
  const body = {
    device_count: deviceCount,
    billing_cycle: billingCycle,
  };
  if (deviceId) body.device_id = deviceId;
  if (coupon) body.coupon = coupon;
  const { data } = await apiClient.post("/billing/subscribe", body);
  return data;
}

/**
 * Request a refund under the money-back guarantee (Req 17.5, 17.7). The backend
 * accepts the request within 14 days of purchase and rejects it after the
 * window has elapsed.
 *
 * @param {{ paymentId?: string, subscriptionId?: string }} input
 * @returns {Promise<object>} the refund result from the gateway
 */
export async function requestRefund({ paymentId, subscriptionId } = {}) {
  const body = {};
  if (paymentId) body.payment_id = paymentId;
  if (subscriptionId) body.subscription_id = subscriptionId;
  const { data } = await apiClient.post("/billing/refund", body);
  return data;
}
