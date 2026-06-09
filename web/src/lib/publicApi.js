import axios from "axios";
import { API_BASE_URL } from "@/lib/apiClient";

// Public (unauthenticated) API surface for the marketing/informational website
// (Task 21.1, Req 31.1, 31.4). These endpoints back the Status and Changelog
// pages and must work for visitors who are not signed in.
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
