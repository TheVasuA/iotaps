/**
 * Resolve REST API base URL at runtime.
 *
 * - dev.iotaps.com / localhost → same-origin `/api/v1` (ingress or Vite proxy)
 * - iotaps.com (Cloudflare Pages) → `https://api.iotaps.com/api/v1` (Pages cannot POST /api)
 * - Otherwise → VITE_API_BASE_URL or `/api/v1`
 */
export function resolveApiBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL || "/api/v1";

  if (typeof window === "undefined") {
    return configured;
  }

  const host = window.location.hostname;

  if (host === "dev.iotaps.com" || host === "localhost" || host === "127.0.0.1") {
    return "/api/v1";
  }

  if (host === "iotaps.com" || host === "www.iotaps.com") {
    if (configured.startsWith("http")) {
      return configured.replace(/\/$/, "");
    }
    return "https://api.iotaps.com/api/v1";
  }

  if (configured.startsWith("/")) {
    return configured;
  }

  return configured.replace(/\/$/, "");
}
