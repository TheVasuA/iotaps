#!/usr/bin/env node
// Build-time SEO asset generator.
//
// Writes sitemap.xml and robots.txt into the Vite output directory so the SPA
// — which has no SSR — at least advertises every marketing URL to crawlers.
// Run automatically as part of `npm run build`; safe to run standalone.
//
// Page HTML itself is not this script's job: scripts/prerender.mjs runs after
// it and renders every marketing route to a real page at its route path,
// FAQPage JSON-LD included. (Before that existed, this script also wrote an
// unstyled FAQ snapshot at a non-route filename so no-JS crawlers could read
// the questions — the prerender supersedes it, since that snapshot could
// never sit at the /faq route path without shadowing the SPA.)
//
//   node scripts/generate-seo.mjs [--out dist]

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  SITE_ORIGIN as DEFAULT_ORIGIN,
  SITE_ROUTES,
  DISALLOWED_PATHS,
} from "../src/lib/siteRoutes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  let outDir = "dist";
  let origin = process.env.VITE_SITE_ORIGIN || DEFAULT_ORIGIN;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--out" && argv[i + 1]) {
      outDir = argv[i + 1];
      i += 1;
    } else if (argv[i] === "--origin" && argv[i + 1]) {
      origin = argv[i + 1];
      i += 1;
    }
  }
  return { outDir, origin };
}

function xmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function toAbsolute(path, origin) {
  if (path === "/") return `${origin}/`;
  return `${origin}${path}`;
}

function buildSitemap(lastmod, origin) {
  const urls = SITE_ROUTES.map((route) => {
    const parts = [
      `    <loc>${xmlEscape(toAbsolute(route.path, origin))}</loc>`,
      `    <lastmod>${lastmod}</lastmod>`,
    ];
    if (route.changefreq) parts.push(`    <changefreq>${xmlEscape(route.changefreq)}</changefreq>`);
    if (route.priority) parts.push(`    <priority>${xmlEscape(route.priority)}</priority>`);
    return `  <url>\n${parts.join("\n")}\n  </url>`;
  }).join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;
}

function buildRobots(origin) {
  const lines = [
    "User-agent: *",
    "Allow: /",
  ];
  for (const path of DISALLOWED_PATHS) {
    lines.push(`Disallow: ${path}`);
  }
  lines.push("");
  lines.push(`Sitemap: ${origin}/sitemap.xml`);
  lines.push("");
  return lines.join("\n");
}

function main() {
  const { outDir, origin } = parseArgs(process.argv.slice(2));
  const targetDir = resolve(__dirname, "..", outDir);
  mkdirSync(targetDir, { recursive: true });

  // Date is only used for <lastmod>, which is content-freshness metadata.
  const lastmod = new Date().toISOString().slice(0, 10);

  const sitemapPath = join(targetDir, "sitemap.xml");
  writeFileSync(sitemapPath, buildSitemap(lastmod, origin), "utf8");

  const robotsPath = join(targetDir, "robots.txt");
  writeFileSync(robotsPath, buildRobots(origin), "utf8");

  console.log(
    `generate-seo: wrote ${SITE_ROUTES.length} URLs → ${sitemapPath}\n` +
      `generate-seo: wrote robots.txt → ${robotsPath}`
  );
}

main();
