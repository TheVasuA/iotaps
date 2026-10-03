// Per-route document metadata for the public marketing surface.
//
// The SPA ships one static <title> from index.html, which means every marketing
// URL would otherwise be indexed under the same title and description. This
// hook sets document.title plus description / Open Graph / Twitter / canonical
// tags on mount so crawlers and social scrapers that run JS see a distinct
// identity per page.
//
// Tags are created on first use and updated in place afterwards, so pages can
// navigate client-side without stacking duplicate <meta> elements. On unmount
// the hook restores whatever was in <head> before it ran — without that, a
// client-side nav from a marketing page to /login or the console would leave
// the previous page's title, canonical, and robots behind (those routes never
// touch this hook).

import { useEffect } from "react";

export const SITE_NAME = "IoTAPS";
export const DEFAULT_TITLE = "IoTAPS — IoT Automation Platform Services";
export const DEFAULT_DESCRIPTION =
  "IoT Automation Platform Services — MQTT device provisioning, live dashboards, rule chains, and billing for teams shipping connected products.";
export const DEFAULT_IMAGE = "/marketing/hero-console-preview.jpg";

/** Promote a page heading to a document title without doubling the brand. */
export function toDocumentTitle(title) {
  if (!title) return DEFAULT_TITLE;
  return /\biotaps\b/i.test(title) ? title : `${title} — ${SITE_NAME}`;
}

function absoluteUrl(pathOrUrl) {
  try {
    return new URL(pathOrUrl, window.location.origin).href;
  } catch {
    return pathOrUrl;
  }
}

/**
 * Upsert a single <meta> or <link> and return a function that undoes it.
 *
 * Existing elements are updated in place and their previous attribute value is
 * restored on undo; elements the hook had to create are removed entirely, so a
 * tag that index.html does not ship cannot outlive the page that introduced it.
 */
function upsert({ tag, attr, key, valueAttr, value }) {
  let el = document.head.querySelector(`${tag}[${attr}="${key}"]`);
  const created = !el;
  if (created) {
    el = document.createElement(tag);
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  const previous = el.getAttribute(valueAttr);
  el.setAttribute(valueAttr, value);

  return function undo() {
    if (created) {
      el.remove();
      return;
    }
    if (previous == null) el.removeAttribute(valueAttr);
    else el.setAttribute(valueAttr, previous);
  };
}

function upsertMeta(nameOrProperty, key, content) {
  return upsert({
    tag: "meta",
    attr: nameOrProperty,
    key,
    valueAttr: "content",
    value: content,
  });
}

function upsertLink(rel, href) {
  return upsert({ tag: "link", attr: "rel", key: rel, valueAttr: "href", value: href });
}

/**
 * Apply document metadata for the current route.
 *
 * @param {object} opts
 * @param {string} [opts.title]        Page heading; promoted to a document title.
 * @param {string} [opts.description]  Meta / OG description.
 * @param {string} [opts.image]        Social preview image (absolute or root-relative).
 * @param {string} [opts.canonical]    Canonical URL; defaults to the current location.
 * @param {boolean} [opts.noindex]     Set robots noindex (for 404 / thin pages).
 */
export function usePageMeta({ title, description, image, canonical, noindex } = {}) {
  useEffect(() => {
    const docTitle = toDocumentTitle(title);
    const desc = description || DEFAULT_DESCRIPTION;
    const imageUrl = absoluteUrl(image || DEFAULT_IMAGE);
    const canonicalUrl = absoluteUrl(canonical || window.location.pathname);

    const previousTitle = document.title;
    document.title = docTitle;

    const undos = [
      upsertMeta("name", "description", desc),
      upsertMeta("name", "robots", noindex ? "noindex, nofollow" : "index, follow"),

      upsertMeta("property", "og:site_name", SITE_NAME),
      upsertMeta("property", "og:type", "website"),
      upsertMeta("property", "og:title", docTitle),
      upsertMeta("property", "og:description", desc),
      upsertMeta("property", "og:image", imageUrl),
      upsertMeta("property", "og:url", canonicalUrl),

      upsertMeta("name", "twitter:card", "summary_large_image"),
      upsertMeta("name", "twitter:title", docTitle),
      upsertMeta("name", "twitter:description", desc),
      upsertMeta("name", "twitter:image", imageUrl),

      upsertLink("canonical", canonicalUrl),
    ];

    return () => {
      document.title = previousTitle;
      for (const undo of undos) undo();
    };
  }, [title, description, image, canonical, noindex]);
}

export default usePageMeta;
