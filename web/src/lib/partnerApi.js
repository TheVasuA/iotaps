import apiClient from "@/lib/apiClient";

// Partner wallet & payout API surface (design.md "Billing, Partner, Referral",
// Req 18.4, 18.5). Each function maps 1:1 to a backend endpoint under
// /api/v1/partner and returns the parsed body. Token handling and tenant
// scoping are applied by the shared apiClient and the backend middleware, so a
// partner only ever sees / withdraws against its own Partner_Wallet.

/**
 * Fetch the caller's Partner_Wallet balance and commission history (Req 18.4).
 *
 * @returns {Promise<{
 *   balance: number|string,
 *   commissions: Array<{
 *     id: string,
 *     amount: number|string,
 *     device_id: string|null,
 *     payment_id: string|null,
 *     period_month: string|null
 *   }>
 * }>}
 */
export async function getWallet() {
  const { data } = await apiClient.get("/partner/wallet");
  return data; // { balance, commissions }
}

/**
 * Request a payout against the wallet balance (Req 18.4, 18.5). The backend
 * persists a PENDING payout for Super_Admin approval when the amount is within
 * the available balance, and rejects it (422 insufficient_balance) when it
 * exceeds the balance — this surface returns whichever outcome the API gives
 * rather than re-checking the balance client-side.
 *
 * @param {{ amount: number, destination?: string }} input
 * @returns {Promise<{
 *   id: string,
 *   wallet_id: string,
 *   amount: number|string,
 *   destination: string|null,
 *   status: string,
 *   requested_at: string|null,
 *   approved_by: string|null,
 *   approved_at: string|null,
 *   razorpayx_payout_id: string|null
 * }>}
 */
export async function requestPayout({ amount, destination } = {}) {
  const body = { amount };
  if (destination) body.destination = destination;
  const { data } = await apiClient.post("/partner/payouts", body);
  return data;
}
