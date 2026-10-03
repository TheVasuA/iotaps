// Source-level guard for the marketing bundle graph. No jsdom: this pins an
// import edge, not rendered output.
//
// BlynkMarketing.jsx pulls LandingReveal (framer-motion) for its scroll
// animations. MarketingSubpage renders every plain content page, so importing
// the typography from BlynkMarketing dragged the ~115KB vendor-motion chunk
// onto about/privacy/terms/faq/… — the same class of problem as having
// framer-motion on the entry modulepreload list, just one level down.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (relative) => readFileSync(join(here, relative), "utf8");

describe("BlynkTypography module isolation", () => {
  it("imports nothing that could pull framer-motion", () => {
    // Check the import graph, not the prose: this file's comment explains why
    // it must not reach BlynkMarketing, and naming that module in the
    // explanation is not the same as importing it.
    const source = read("BlynkTypography.jsx");
    const imports = [...source.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1]);
    expect(imports).toEqual(["@/lib/utils"]);
    for (const spec of imports) {
      expect(spec).not.toMatch(/framer-motion|LandingReveal|BlynkMarketing/);
    }
  });

  it("MarketingSubpage takes the typography from BlynkTypography, not BlynkMarketing", () => {
    const source = read("../MarketingSubpage.jsx");
    expect(source).toMatch(/from\s+"@\/components\/public\/blynk\/BlynkTypography"/);
    expect(source).not.toMatch(/from\s+"@\/components\/public\/blynk\/BlynkMarketing"/);
  });

  it("BlynkMarketing re-exports the typography for landing callers", () => {
    const source = read("BlynkMarketing.jsx");
    expect(source).toMatch(
      /import\s*\{[^}]*BlynkEyebrow[^}]*\}\s*from\s*"@\/components\/public\/blynk\/BlynkTypography"/
    );
    expect(source).toMatch(/export\s*\{[^}]*BlynkEyebrow[^}]*\}/);
  });
});
