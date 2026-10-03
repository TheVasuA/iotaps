// Regression guards for marketing heading hierarchy.
//
// MarketingPageHero renders the page title as <h1>, so any body heading that
// sits directly under it must be <h2>. Skipping to <h3> (or rendering the hero
// as <h2> under a missing <h1>) is an accessibility and SEO defect that does
// not fail the build or the page visually — only a source-level check catches it.

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const webSrc = join(__dirname, "..");

const read = (rel) => readFileSync(join(webSrc, rel), "utf8");

describe("marketing heading hierarchy", () => {
  it("renders the page hero title as an h1", () => {
    const hero = read("components/public/MarketingSubpage.jsx");
    expect(hero).toMatch(/as="h1"/);
  });

  it("renders MarketingProse section headings as h2, not h3", () => {
    // These sit directly under the hero h1 on About, Privacy, Terms, etc.
    const prose = read("components/public/MarketingSubpage.jsx");
    const block = prose.slice(prose.indexOf("MarketingProse"), prose.indexOf("MarketingBottomCta"));
    expect(block).toMatch(/<h2\b/);
    expect(block).not.toMatch(/<h3\b/);
  });

  it("renders card-grid and blog-list titles as h2, not h3", () => {
    const page = read("pages/public/marketing/createMarketingPage.jsx");
    for (const component of ["MarketingCardGrid", "MarketingBlogList"]) {
      const start = page.indexOf(`export function ${component}`);
      expect(start).toBeGreaterThan(-1);
      const end = page.indexOf("export function", start + 1);
      const block = page.slice(start, end === -1 ? undefined : end);
      expect(block).toMatch(/<h2\b/);
      expect(block).not.toMatch(/<h3\b/);
    }
  });

  it("never lets a marketing page jump from hero h1 straight to h3", () => {
    // Body copy that renders its own section titles must use h2 while the hero
    // is the only h1 on the page. Flag any remaining top-level <h3> in the
    // marketing surface that is not preceded by an <h2> in the same file.
    const files = [
      "pages/public/ContactPage.jsx",
      "pages/public/marketing/marketingPages.jsx",
      "components/public/MarketingSubpage.jsx",
      "pages/public/marketing/createMarketingPage.jsx",
      "pages/public/BlynkAlternativePage.jsx",
    ];
    for (const rel of files) {
      const source = read(rel);
      const hasHeroH1 = /as="h1"|<h1\b/.test(source) || /MarketingShell|MarketingPageHero|MarketingProse/.test(source);
      if (!hasHeroH1) continue;
      const h3s = [...source.matchAll(/<h3\b/g)].length;
      const h2s = [...source.matchAll(/<h2\b/g)].length;
      // h3 is only legal once an h2 already exists in the same component tree.
      if (h3s > 0) {
        expect(
          h2s,
          `${rel} renders <h3> without any <h2> under the page's <h1> hero`
        ).toBeGreaterThan(0);
      }
    }
  });
});
