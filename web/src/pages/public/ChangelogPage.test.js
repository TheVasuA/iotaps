// Source-level guards for the public Changelog page's tri-state rendering
// (Task 21.1, Req 31.1). The page must distinguish a failed feed load from a
// genuinely empty one: conflating them makes a real outage indistinguishable
// from "No updates yet". No jsdom is used - these assert on the source, the
// same style as src/lib/marketingHeadings.test.js.

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, "ChangelogPage.jsx"), "utf8");

describe("ChangelogPage tri-state rendering", () => {
  it("keeps the error branch distinct from the empty-feed branch", () => {
    // The old conflation (`state === "error" || entries.length === 0`) must
    // not come back: an outage and an empty feed are different states.
    expect(source).not.toMatch(/state === "error"\s*\|\|/);
    expect(source).toMatch(/state === "error"\s*\?/);
    expect(source).toMatch(/entries\.length === 0\s*\?/);
  });

  it("renders a distinct error card with a Retry action", () => {
    expect(source).toContain("Could not load updates");
    expect(source).toMatch(/onClick=\{retry\}/);
    expect(source).toMatch(/>[\s]*Retry[\s]*</);
  });

  it("keeps the empty-feed card for a successful empty list", () => {
    expect(source).toContain("No updates yet");
    expect(source).toContain("Published updates will appear here.");
  });

  it("retry re-runs the fetch and returns to the loading state", () => {
    expect(source).toMatch(/setState\("loading"\)/);
    expect(source).toMatch(/const retry = \(\) => setReloadKey/);
    // The effect must depend on the reload key, or retry would never refetch.
    expect(source).toMatch(/\}, \[reloadKey\]\);/);
  });
});
