// Canonical list of indexable marketing routes.
//
// Shared by the build-time SEO generator (scripts/generate-seo.mjs) and by
// anything else that needs to enumerate the public surface. Keep this in sync
// with the public children of the "/" route in src/router.jsx — every path here
// must resolve to a real page, or it will land in the sitemap as a 404.

// Prefer Vite-injected site origin when building for a specific domain; the
// generator script can override via --origin. Kept free of `process` so this
// module is safe to import from the browser bundle.
export const SITE_ORIGIN = "https://iotaps.com";

/**
 * @typedef {object} SiteRoute
 * @property {string} path        Absolute path, no trailing slash (except "/").
 * @property {string} [changefreq] sitemap changefreq hint.
 * @property {string} [priority]   sitemap priority hint (0.0–1.0).
 */

/** @type {SiteRoute[]} */
export const SITE_ROUTES = [
  { path: "/", changefreq: "weekly", priority: "1.0" },
  { path: "/platform", changefreq: "weekly", priority: "0.9" },
  { path: "/pricing", changefreq: "weekly", priority: "0.9" },
  { path: "/solutions", changefreq: "weekly", priority: "0.8" },
  { path: "/solutions/industrial-iot", changefreq: "monthly", priority: "0.7" },
  { path: "/solutions/smart-agriculture", changefreq: "monthly", priority: "0.7" },
  { path: "/solutions/energy-hvac", changefreq: "monthly", priority: "0.7" },
  { path: "/blynk-alternative", changefreq: "monthly", priority: "0.7" },
  { path: "/enterprise", changefreq: "monthly", priority: "0.8" },
  { path: "/developers", changefreq: "weekly", priority: "0.8" },
  { path: "/developers/mqtt-devices", changefreq: "monthly", priority: "0.7" },
  { path: "/developers/dashboards-api", changefreq: "monthly", priority: "0.7" },
  { path: "/docs", changefreq: "weekly", priority: "0.8" },
  { path: "/partners", changefreq: "monthly", priority: "0.6" },
  { path: "/blog", changefreq: "weekly", priority: "0.6" },
  { path: "/case-studies", changefreq: "monthly", priority: "0.6" },
  { path: "/security", changefreq: "yearly", priority: "0.5" },
  { path: "/about", changefreq: "monthly", priority: "0.5" },
  { path: "/contact", changefreq: "monthly", priority: "0.6" },
  { path: "/faq", changefreq: "monthly", priority: "0.6" },
  { path: "/status", changefreq: "weekly", priority: "0.5" },
  { path: "/changelog", changefreq: "weekly", priority: "0.5" },
  { path: "/terms", changefreq: "yearly", priority: "0.3" },
  { path: "/privacy", changefreq: "yearly", priority: "0.3" },
  { path: "/refund-policy", changefreq: "yearly", priority: "0.3" },
];

/** Paths that must never be indexed (auth, app shell, admin, errors). */
export const DISALLOWED_PATHS = [
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/get-started",
  "/dashboard",
  "/homepage",
  "/devices",
  "/flasher",
  "/explorer",
  "/custom-data",
  "/locations",
  "/organizations",
  "/snapshots",
  "/fleet",
  "/rules",
  "/billing",
  "/referrals",
  "/wallet",
  "/support",
  "/org",
  "/settings",
  "/admin",
];
