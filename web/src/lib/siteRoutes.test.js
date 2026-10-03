// Guards for the marketing route registry used to build sitemap.xml/robots.txt.
//
// The sitemap is generated at build time from SITE_ROUTES, so a stale entry
// ships a crawlable 404 and a missing entry silently drops a page from search.
// These tests pin the invariants that would otherwise drift.

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { SITE_ROUTES, DISALLOWED_PATHS, SITE_ORIGIN } from "./siteRoutes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const routerSource = readFileSync(join(__dirname, "../router.jsx"), "utf8");

/** Pull the public route paths out of the router's "/" children. */
function publicRouterPaths() {
  // The public branch runs from `path: "/"` up to the first non-child route
  // (`/login`). Child paths are relative there, so "pricing" means "/pricing".
  const start = routerSource.indexOf('path: "/"');
  const end = routerSource.indexOf('path: "/login"');
  const block = routerSource.slice(start, end === -1 ? undefined : end);

  const paths = [...block.matchAll(/path:\s*"([^"]+)"/g)]
    .map((m) => m[1])
    // "*" is the 404 splat, not a real content route.
    .filter((p) => p !== "*")
    .map((p) => (p.startsWith("/") ? p : `/${p}`));

  // `{ index: true }` serves the home route without naming a path.
  if (/index:\s*true/.test(block)) paths.push("/");
  return paths;
}

describe("SITE_ROUTES", () => {
  it("is non-empty and sorted home-first", () => {
    expect(SITE_ROUTES.length).toBeGreaterThan(10);
    expect(SITE_ROUTES[0].path).toBe("/");
  });

  it("uses absolute paths with no trailing slash (except home)", () => {
    for (const route of SITE_ROUTES) {
      expect(route.path.startsWith("/")).toBe(true);
      if (route.path !== "/") {
        expect(route.path.endsWith("/")).toBe(false);
      }
    }
  });

  it("has no duplicate paths", () => {
    const paths = SITE_ROUTES.map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("every entry has a valid sitemap priority", () => {
    for (const route of SITE_ROUTES) {
      const p = Number.parseFloat(route.priority);
      expect(Number.isNaN(p)).toBe(false);
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(1);
    }
  });

  it("only uses known changefreq values", () => {
    const allowed = new Set([
      "always",
      "hourly",
      "daily",
      "weekly",
      "monthly",
      "yearly",
      "never",
    ]);
    for (const route of SITE_ROUTES) {
      expect(allowed.has(route.changefreq)).toBe(true);
    }
  });

  it("does not list any route the router does not serve", () => {
    // The sitemap must never advertise a URL that 404s.
    const routerPaths = new Set(publicRouterPaths());
    const missing = SITE_ROUTES.map((r) => r.path).filter((p) => !routerPaths.has(p));
    expect(missing).toEqual([]);
  });

  it("lists the Blynk-alternative migration page in both the registry and the router", () => {
    // Named explicitly so a later refactor of either table cannot drop this
    // comparison/migration landing page from the sitemap unnoticed.
    expect(SITE_ROUTES.map((r) => r.path)).toContain("/blynk-alternative");
    expect(publicRouterPaths()).toContain("/blynk-alternative");
  });

  it("lists every public router route except the catch-all", () => {
    // And a marketing page must not be silently absent from the sitemap.
    const listed = new Set(SITE_ROUTES.map((r) => r.path));
    const unlisted = publicRouterPaths().filter((p) => !listed.has(p));
    expect(unlisted).toEqual([]);
  });

  it("never lists a disallowed path", () => {
    for (const route of SITE_ROUTES) {
      expect(DISALLOWED_PATHS).not.toContain(route.path);
    }
  });
});

describe("DISALLOWED_PATHS", () => {
  it("are absolute and never bare slashes", () => {
    for (const path of DISALLOWED_PATHS) {
      expect(path.startsWith("/")).toBe(true);
      expect(path).not.toBe("/");
    }
  });

  it("has no duplicates", () => {
    expect(new Set(DISALLOWED_PATHS).size).toBe(DISALLOWED_PATHS.length);
  });

  it("covers the auth and app entry points", () => {
    for (const required of ["/login", "/register", "/admin", "/settings", "/dashboard"]) {
      expect(DISALLOWED_PATHS).toContain(required);
    }
  });
});

describe("SITE_ORIGIN", () => {
  it("is an https origin with no trailing slash", () => {
    expect(SITE_ORIGIN.startsWith("https://")).toBe(true);
    expect(SITE_ORIGIN.endsWith("/")).toBe(false);
  });

  it("has no path component", () => {
    expect(new URL(SITE_ORIGIN).pathname).toBe("/");
  });
});
