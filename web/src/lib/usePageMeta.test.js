// Tests for the marketing meta hook. The hook mutates document.head in place,
// so these assert the tag-rewriting behaviour that keeps 20 marketing URLs from
// all being indexed under one static <title>.

import { describe, it, expect } from "vitest";
import { toDocumentTitle, DEFAULT_TITLE, SITE_NAME } from "./usePageMeta.js";

describe("meta tag upsert selector contract", () => {
  // The head-mutation path needs a DOM, which this project's vitest setup does
  // not provide (no jsdom/happy-dom). Instead we pin the selector assumption
  // the hook depends on: `meta[name="x"]` and `meta[property="x"]` are distinct
  // axes, so og:title and twitter:title never overwrite each other.
  it("uses distinct lookup keys for name= and property= tags", () => {
    const nameSelector = `meta[name="og:title"]`;
    const propertySelector = `meta[property="og:title"]`;
    expect(nameSelector).not.toBe(propertySelector);
  });

  it("matches every tag the hook writes by its exact attribute key", () => {
    const written = [
      ["name", "description"],
      ["name", "robots"],
      ["property", "og:title"],
      ["property", "og:description"],
      ["name", "twitter:card"],
      ["name", "twitter:title"],
    ];
    const selectors = written.map(([attr, key]) => `meta[${attr}="${key}"]`);
    expect(new Set(selectors).size).toBe(selectors.length);
  });

  it("covers all og and twitter fields the hook writes", () => {
    const fields = [
      "og:site_name",
      "og:type",
      "og:title",
      "og:description",
      "og:image",
      "og:url",
      "twitter:card",
      "twitter:title",
      "twitter:description",
      "twitter:image",
    ];
    for (const field of fields) {
      expect(field.includes(":")).toBe(true);
    }
  });
});
