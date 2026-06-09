import apiClient from "@/lib/apiClient";

// Referral program API surface (design.md "Billing, Partner, Referral", Req 19).
// Maps 1:1 to the backend endpoint under /api/v1/referrals and returns the
// parsed body. Token handling and tenant scoping are applied by the shared
// apiClient and the backend middleware.

/**
 * Fetch the caller's referral summary: their shareable referral code, confirmed
 * referral count, and any granted referral rewards (Req 19.1, 19.2).
 *
 * @returns {Promise<{
 *   code: string,
 *   count: number,
 *   rewards: Array<{
 *     devices_granted: number,
 *     months_granted: number,
 *     granted_at: string|null,
 *     expires_at: string|null
 *   }>
 * }>}
 */
export async function getReferralSummary() {
  const { data } = await apiClient.get("/referrals");
  return data; // { code, count, rewards }
}
