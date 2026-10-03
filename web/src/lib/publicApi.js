import axios from "axios";
import { API_BASE_URL } from "@/lib/apiClient";

// Public (unauthenticated) API surface for the marketing/informational website
// (Task 21.1, Req 31.1, 31.4). These endpoints back the Status, Changelog and
// Pricing pages and must work for visitors who are not signed in.
//
// We use a bare axios instance (not the shared apiClient) so the public site
// never triggers the auth refresh/clear interceptor: a visitor with no session
// should simply see an empty/unavailable state rather than have token storage
// mutated. Token handling for the authenticated app stays in apiClient.

const publicClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

/**
 * Fetch the live operational status of platform services for the Status page
 * (Req 31.4). Maps to the public GET /health endpoint, returning overall API
 * health plus per-dependency status.
 *
 * @returns {Promise<{
 *   status: "ok"|"degraded",
 *   service: string,
 *   dependencies: Array<{ name: string, status: string }>
 * }>}
 */
export async function getServiceStatus() {
  const { data } = await publicClient.get("/health");
  return data; // { status, service, dependencies }
}

/**
 * Fetch published changelog entries for the public Changelog page (Req 31.1).
 * Maps to GET /changelog and unwraps the { entries } envelope.
 *
 * @returns {Promise<Array<{
 *   id: string, version: string|null, title: string|null,
 *   body: string|null, published_at: string|null
 * }>>}
 */
export async function getPublicChangelog() {
  const { data } = await publicClient.get("/changelog");
  return data.entries ?? [];
}

/**
 * Map the snake_case GET /billing/plans body onto the display shape the
 * pricing UI renders: camelCase volume tiers plus the annual unit price.
 * Returns null when the body is unusable so callers can fall back to the
 * bundled @/lib/pricing mirror instead of blanking the page.
 *
 * @param {object} body
 * @returns {{annualUnitPrice: number, tiers: Array<{minDevices: number, maxDevices: number|null, unitPriceMonthly: number}>}|null}
 */
export function normalizePlans(body) {
  const tiers = body?.pricing_tiers;
  const annualUnitPrice = body?.pro?.annual_unit_price;
  if (!Array.isArray(tiers) || tiers.length === 0) return null;
  if (typeof annualUnitPrice !== "number" || !Number.isFinite(annualUnitPrice)) {
    return null;
  }
  const mapped = tiers.map((tier) => ({
    minDevices: tier?.min_devices,
    maxDevices: tier?.max_devices ?? null,
    unitPriceMonthly: tier?.unit_price_monthly,
  }));
  if (
    mapped.some(
      (tier) =>
        typeof tier.minDevices !== "number" ||
        typeof tier.unitPriceMonthly !== "number"
    )
  ) {
    return null;
  }
  return { annualUnitPrice, tiers: mapped };
}

/**
 * Fetch the Free/Pro plans and volume-discount tiers for the public Pricing
 * page (Req 16.1-16.5). Maps to GET /billing/plans, a pure pricing read that
 * works for visitors who are not signed in, and normalises the snake_case
 * body via {@link normalizePlans} (null when unusable).
 *
 * @returns {Promise<{annualUnitPrice: number, tiers: Array<{minDevices: number, maxDevices: number|null, unitPriceMonthly: number}>}|null>}
 */
export async function getPublicPlans() {
  const { data } = await publicClient.get("/billing/plans");
  return normalizePlans(data);
}
