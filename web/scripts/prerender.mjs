#!/usr/bin/env node
// Build-time prerenderer for the marketing surface.
//
// The SPA has no SSR, so a hard load of /faq (or any marketing URL) only
// serves the empty Vite shell until the JS boots. This script runs AFTER
// `vite build` and renders every route in SITE_ROUTES to real page HTML at the
// route path — dist/faq/index.html, dist/pricing/index.html, … — by loading
// the actual React route tree through Vite in SSR mode and rendering each
// location with ReactDOMServer.
//
// The prerendered document is the built dist/index.html with the rendered
// markup injected into #root and per-route <title> / meta / canonical / og:
// tags rewritten. The built modulepreload + <script type="module"> tags stay
// in place, so a JS-capable browser still boots the real React app over the
// static content (createRoot replaces it). That is what makes this a drop-in
// replacement at the route path rather than a dead-end snapshot: no-JS
// crawlers and readers get a complete styled page, everyone else gets the SPA.
//
// Routes are enumerated from SITE_ROUTES at runtime — never a hardcoded list —
// so a route added to src/lib/siteRoutes.js is picked up by the next build.
// A route that fails to render is skipped with a warning and falls back to the
// SPA shell; a missing prerender is fine, a broken one is not.
//
//   node scripts/prerender.mjs [--out dist] [--origin https://iotaps.com]

import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Writable } from "node:stream";
import { createElement as h } from "react";
import { renderToPipeableStream } from "react-dom/server";
import { createMemoryRouter, RouterProvider, matchRoutes } from "react-router-dom";
import { createServer } from "vite";

import { SITE_ORIGIN as DEFAULT_ORIGIN, SITE_ROUTES } from "../src/lib/siteRoutes.js";
import { faqJsonLdScriptText } from "../src/lib/faqData.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(__dirname, "..");

const RENDER_TIMEOUT_MS = 20000;

// Mirrors the exported constants and fallbacks of src/lib/usePageMeta.js. The
// recorder stub below and applyHeadMeta must both fall back the way the real
// hook does, so the prerendered <head> ends up with exactly the values the SPA
// would have written on mount (and never with a tag the hook would have filled).
const SITE_NAME = "IoTAPS";
const DEFAULT_TITLE = "IoTAPS — IoT Automation Platform Services";
const DEFAULT_DESCRIPTION =
  "IoT Automation Platform Services — MQTT device provisioning, live dashboards, rule chains, and billing for teams shipping connected products.";
const DEFAULT_IMAGE = "/marketing/hero-console-preview.jpg";

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Document metadata
//
// Marketing pages declare title/description through usePageMeta, a useEffect
// that never runs on the server. The Vite plugin below swaps that module for a
// recorder while prerendering: the hook still runs during render, and its
// arguments are collected here so the <head> can be rewritten per route with
// exactly the values the SPA would have applied on mount.
// ---------------------------------------------------------------------------

const META_COLLECTOR = "__iotapsPrerenderMeta";

function installMetaCollector() {
  globalThis[META_COLLECTOR] = [];
}

function takeMeta() {
  const entries = globalThis[META_COLLECTOR] || [];
  globalThis[META_COLLECTOR] = [];
  // Last call wins: a page and its shell both may set metadata; the innermost
  // (most specific) call is the one the browser would end up with too.
  return entries.length ? entries[entries.length - 1] : null;
}

const USE_PAGE_META_MODULE_ID = "\0prerender-usePageMeta";

// Stand-in for src/lib/usePageMeta.js. Mirrors its exported surface (the
// marketing modules import the named constants from it) and records what the
// real hook would have written to <head> instead of writing it. The constants
// come from the same values applyHeadMeta uses, so the two cannot drift.
const USE_PAGE_META_STUB = `
export const SITE_NAME = ${JSON.stringify(SITE_NAME)};
export const DEFAULT_TITLE = ${JSON.stringify(DEFAULT_TITLE)};
export const DEFAULT_DESCRIPTION = ${JSON.stringify(DEFAULT_DESCRIPTION)};
export const DEFAULT_IMAGE = ${JSON.stringify(DEFAULT_IMAGE)};
export function toDocumentTitle(title) {
  if (!title) return DEFAULT_TITLE;
  return /\\biotaps\\b/i.test(title) ? title : title + " — " + SITE_NAME;
}
export function usePageMeta(meta) {
  const sink = globalThis.__iotapsPrerenderMeta;
  if (sink && meta) sink.push(meta);
  return undefined;
}
export default usePageMeta;
`;

function metaRecorderPlugin() {
  return {
    name: "prerender:use-page-meta-recorder",
    // `pre` so this runs before Vite's alias plugin rewrites "@/lib/usePageMeta"
    // into a filesystem path; both spellings are still matched below.
    enforce: "pre",
    resolveId(id) {
      if (
        id === "@/lib/usePageMeta" ||
        id.endsWith("/lib/usePageMeta") ||
        id.endsWith("/lib/usePageMeta.js")
      ) {
        return USE_PAGE_META_MODULE_ID;
      }
      return null;
    },
    load(id) {
      return id === USE_PAGE_META_MODULE_ID ? USE_PAGE_META_STUB : null;
    },
  };
}

// Per-route structured data that pages attach from useEffect (which does not
// run on the server). Mirrors the block src/pages/public/FaqPage.jsx injects
// client-side so no-JS crawlers keep seeing the FAQPage JSON-LD.
const STRUCTURED_DATA = {
  "/faq": () => faqJsonLdScriptText(),
};

// ---------------------------------------------------------------------------
// HTML template injection
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function absoluteUrl(pathOrUrl, origin) {
  if (/^[a-z][a-z0-9+.-]*:/i.test(pathOrUrl)) return pathOrUrl;
  const path = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  return `${origin}${path}`;
}

function toDocumentTitle(title) {
  if (!title) return DEFAULT_TITLE;
  return /\biotaps\b/i.test(title) ? title : `${title} — ${SITE_NAME}`;
}

/**
 * Rewrite the <head> of the built shell for one route.
 *
 * The template is the Vite output derived from index.html, whose tag set is
 * fixed, so targeted attribute replacements are safe — and they leave the
 * built stylesheet/modulepreload/script tags exactly where they are.
 *
 * Fallbacks match usePageMeta exactly: an absent description becomes
 * DEFAULT_DESCRIPTION (never an emptied tag), an absent image DEFAULT_IMAGE,
 * and an absent title DEFAULT_TITLE.
 */
function applyHeadMeta(html, { title, description, image, canonical, noindex }, origin) {
  const docTitle = toDocumentTitle(title);
  const desc = description || DEFAULT_DESCRIPTION;
  const imageUrl = absoluteUrl(image || DEFAULT_IMAGE, origin);
  const canonicalUrl = absoluteUrl(canonical, origin);

  const replacements = [
    [/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(docTitle)}</title>`],
    [/(<meta\s+name="description"\s+content=")[^"]*(")/, `$1${escapeHtml(desc)}$2`],
    [/(<meta\s+name="robots"\s+content=")[^"]*(")/, `$1${noindex ? "noindex, nofollow" : "index, follow"}$2`],
    [/(<meta\s+property="og:title"\s+content=")[^"]*(")/, `$1${escapeHtml(docTitle)}$2`],
    [/(<meta\s+property="og:description"\s+content=")[^"]*(")/, `$1${escapeHtml(desc)}$2`],
    [/(<meta\s+property="og:image"\s+content=")[^"]*(")/, `$1${escapeHtml(imageUrl)}$2`],
    [/(<meta\s+property="og:url"\s+content=")[^"]*(")/, `$1${escapeHtml(canonicalUrl)}$2`],
    [/(<meta\s+name="twitter:title"\s+content=")[^"]*(")/, `$1${escapeHtml(docTitle)}$2`],
    [/(<meta\s+name="twitter:description"\s+content=")[^"]*(")/, `$1${escapeHtml(desc)}$2`],
    [/(<meta\s+name="twitter:image"\s+content=")[^"]*(")/, `$1${escapeHtml(imageUrl)}$2`],
    [/(<link\s+rel="canonical"\s+href=")[^"]*(")/, `$1${escapeHtml(canonicalUrl)}$2`],
  ];

  let out = html;
  for (const [pattern, replacement] of replacements) {
    if (pattern.test(out)) {
      out = out.replace(pattern, replacement);
    }
  }
  return out;
}

function injectStructuredData(html, routePath) {
  const build = STRUCTURED_DATA[routePath];
  if (!build) return html;
  const tag = `<script type="application/ld+json">${build()}</script>`;
  return html.replace("</head>", `    ${tag}\n  </head>`);
}

/**
 * Inject rendered markup into the built shell.
 *
 * The static tree is the same one createRoot will replace on boot, so the
 * prerendered page is the real page for no-JS readers and a fast first paint
 * for everyone else. Matches an empty or previously-prerendered #root (the
 * element spans whatever sits directly before </body>), so re-running the
 * script against an already-prerendered dist replaces the content in place.
 */
function injectAppHtml(shellHtml, appHtml) {
  // The entry script lives in <head> (Vite 5 hoists module scripts there), so
  // the #root element is whatever sits directly before </body>.
  const marker = /(<div id="root">)[\s\S]*?(<\/div>\s*<\/body>)/;
  if (!marker.test(shellHtml)) {
    throw new Error('built shell has no <div id="root"></div> to inject into');
  }
  return shellHtml.replace(marker, `$1${appHtml}$2`);
}

function outputPathsFor(routePath, targetDir) {
  if (routePath === "/") return join(targetDir, "index.html");
  const segments = routePath.split("/").filter(Boolean);
  return join(targetDir, ...segments, "index.html");
}

/**
 * Remove every output a previous prerender wrote, before writing new ones.
 *
 * A skipped route must fall back to the SPA, and an empty route directory
 * would defeat that: nginx `try_files $uri $uri/ /index.html` matches the
 * directory and then 404s on its missing index instead of reaching the SPA
 * fallback. Clearing up front (rather than only on skip) keeps the invariant
 * simple: whatever exists under a route path after this script runs was
 * rendered successfully by this run.
 */
function clearPreviousOutputs(targetDir) {
  for (const { path: routePath } of SITE_ROUTES) {
    if (routePath === "/") continue;
    const segments = routePath.split("/").filter(Boolean);
    rmSync(join(targetDir, ...segments), { recursive: true, force: true });
  }
  // The pre-prerender SEO side-channel (an unstyled snapshot of the FAQ at a
  // non-route filename) exists only when a stale dist is reused; remove it so
  // it can never be mistaken for the real page at /faq.
  rmSync(join(targetDir, "faq.html"), { force: true });
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/**
 * Minimal browser surface for src/router.jsx, which calls createBrowserRouter
 * at module scope and so needs window.history during import. Nothing here is
 * used during rendering — the prerender runs each location through
 * createMemoryRouter instead of the browser history the real router binds.
 */
function installBrowserShims() {
  // framer-motion (LandingReveal and friends) does `element instanceof
  // SVGElement` while rendering, so the constructor has to exist on the server.
  // Plain classes are enough: every use is an instanceof check.
  class HTMLElement {}
  class SVGElement extends HTMLElement {}
  class Element extends HTMLElement {}
  globalThis.HTMLElement = HTMLElement;
  globalThis.SVGElement = SVGElement;
  globalThis.Element = Element;
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });

  const historyState = { usr: null, key: "default" };
  const win = {
    history: {
      state: historyState,
      pushState: () => {},
      replaceState: () => {},
      go: () => {},
    },
    location: {
      pathname: "/",
      search: "",
      hash: "",
      origin: DEFAULT_ORIGIN,
      href: `${DEFAULT_ORIGIN}/`,
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    confirm: () => false,
  };
  const doc = {
    title: "",
    head: null,
    body: null,
    baseURI: `${DEFAULT_ORIGIN}/`,
    // @remix-run/router resolves `window` as `options.window ?? document.defaultView`.
    defaultView: win,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ setAttribute() {}, getAttribute: () => null, appendChild() {} }),
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  win.document = doc;
  globalThis.window = win;
  globalThis.document = doc;
}

/** Render one location to static markup, bounded by RENDER_TIMEOUT_MS. */
function renderRoute(routes, routePath) {
  return new Promise((resolve, reject) => {
    const router = createMemoryRouter(routes, { initialEntries: [routePath] });
    const chunks = [];
    const sink = new Writable({
      write(chunk, _enc, cb) {
        chunks.push(chunk.toString());
        cb();
      },
    });

    installMetaCollector();

    // react-router's <Link> calls useLayoutEffect, which React warns about on
    // every link of every prerendered page. It is a known false alarm here
    // (effects never run in a static render); real render failures surface
    // through onError below. Filter just that warning so build output stays
    // readable.
    const originalConsoleError = console.error;
    console.error = (...args) => {
      const text = args.map((a) => (typeof a === "string" ? a : a?.message ?? "")).join(" ");
      if (text.includes("useLayoutEffect does nothing on the server")) return;
      originalConsoleError(...args);
    };

    let settled = false;
    let renderError = null;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      console.error = originalConsoleError;
      fn(value);
    };

    const timer = setTimeout(() => {
      try {
        stream?.abort();
      } catch {
        // abort() throws if the stream already closed; the timeout is stale.
      }
      finish(reject, new Error(`render timed out after ${RENDER_TIMEOUT_MS}ms`));
    }, RENDER_TIMEOUT_MS);

    let stream;
    try {
      stream = renderToPipeableStream(h(RouterProvider, { router }), {
        // Fires once every lazy route module has resolved and every Suspense
        // boundary above the fold has settled — i.e. when the static markup is
        // complete rather than holding React.lazy fallbacks.
        onAllReady() {
          if (renderError) {
            finish(reject, renderError);
            return;
          }
          stream.pipe(sink);
          // pipe() is synchronous for a fully-ready render; give the last
          // flush a tick before reading the collected chunks.
          setTimeout(() => finish(resolve, chunks.join("")), 50);
        },
        onError(err) {
          // React reports render errors here and may still finish the stream —
          // behind a router error boundary, which would publish an error page as
          // if it were the marketing page. Any error means the output is not
          // trustworthy, so the route is skipped instead of written.
          renderError = err instanceof Error ? err : new Error(String(err));
          console.warn(
            `prerender: render error at ${routePath}: ${renderError.message}`,
            renderError.stack ? `\n${renderError.stack}` : ""
          );
        },
        onShellError(err) {
          // The shell itself failed; onAllReady will never fire.
          const error = err instanceof Error ? err : new Error(String(err));
          console.warn(`prerender: shell render failed at ${routePath}: ${error.message}`);
          finish(reject, error);
        },
      });
    } catch (err) {
      console.error = originalConsoleError;
      throw err;
    }
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const { outDir, origin } = parseArgs(process.argv.slice(2));
  const targetDir = resolve(WEB_ROOT, outDir);
  const shellPath = join(targetDir, "index.html");

  if (!existsSync(shellPath)) {
    console.warn(
      `prerender: no ${shellPath} — run \`vite build\` first; skipping prerender.`
    );
    return;
  }

  const shellHtml = readFileSync(shellPath, "utf8");

  clearPreviousOutputs(targetDir);

  installBrowserShims();

  const vite = await createServer({
    root: WEB_ROOT,
    logLevel: "warn",
    appType: "custom",
    server: { middlewareMode: true, hmr: false, watch: null },
    optimizeDeps: { noDiscovery: true },
    plugins: [metaRecorderPlugin()],
  });

  let rendered = 0;
  let skipped = 0;

  try {
    // The live route table is the single source of truth for what renders
    // where: importing router.jsx (rather than a second hand-kept map) means a
    // route added there is prerendered without touching this script.
    const routerModule = await vite.ssrLoadModule("/src/router.jsx");
    const appRouter = routerModule.router ?? routerModule.default;
    const routes = appRouter.routes;

    for (const { path: routePath } of SITE_ROUTES) {
      const outFile = outputPathsFor(routePath, targetDir);
      const matched = matchRoutes(routes, routePath);
      if (!matched?.length) {
        console.warn(`prerender: no route matches ${routePath} — leaving the SPA shell in place.`);
        skipped += 1;
        continue;
      }

      let pageHtml;
      try {
        pageHtml = await renderRoute(routes, routePath);
      } catch (err) {
        console.warn(`prerender: skipping ${routePath} (${err?.message ?? err}); SPA fallback stays.`);
        skipped += 1;
        continue;
      }

      // takeMeta() is null when the page never calls usePageMeta — then the SPA
      // would leave the template <head> alone, and so do we. Only a hook call
      // justifies a rewrite, and then with the hook's own fallbacks.
      const meta = takeMeta();
      const headHtml = meta
        ? applyHeadMeta(
            shellHtml,
            {
              title: meta.title,
              description: meta.description,
              image: meta.image,
              canonical: meta.canonical || routePath,
              noindex: meta.noindex,
            },
            origin
          )
        : shellHtml;
      const html = injectStructuredData(injectAppHtml(headHtml, pageHtml), routePath);

      mkdirSync(dirname(outFile), { recursive: true });
      writeFileSync(outFile, html, "utf8");
      rendered += 1;
    }

    console.log(
      `prerender: ${rendered} route(s) written to ${targetDir}` +
        (skipped ? `, ${skipped} skipped (SPA fallback)` : "")
    );
  } finally {
    await vite.close();
  }
}

main().catch((err) => {
  console.error("prerender: fatal —", err);
  process.exitCode = 1;
});
