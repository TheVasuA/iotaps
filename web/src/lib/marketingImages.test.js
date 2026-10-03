// Pure-function tests for the srcset builder. No jsdom: MarketingImage itself
// is a component and cannot be rendered under this Vitest setup, so these pin
// the string shaping that decides what a browser is offered.

import { describe, it, expect } from "vitest";
import { buildSrcSet, marketingImageSizes } from "./marketingImages.js";

const variants = [
  { url: "/marketing/optimized/a-800.webp", width: 800, height: 534 },
  { url: "/marketing/optimized/a.webp", width: 1600, height: 1067 },
];

describe("buildSrcSet", () => {
  it("emits ascending NNNw candidates from variant objects", () => {
    expect(buildSrcSet(variants)).toBe(
      "/marketing/optimized/a-800.webp 800w, /marketing/optimized/a.webp 1600w"
    );
  });

  it("returns a bare URL unchanged (legacy single-candidate shape)", () => {
    expect(buildSrcSet("/marketing/optimized/a.webp")).toBe("/marketing/optimized/a.webp");
  });

  it("drops entries with no width so a bad manifest never emits a broken descriptor", () => {
    expect(buildSrcSet([{ url: "/x.webp" }, { url: "/y.webp", width: 400 }])).toBe("/y.webp 400w");
  });

  it("returns undefined rather than an empty srcset when nothing is usable", () => {
    expect(buildSrcSet(undefined)).toBeUndefined();
    expect(buildSrcSet([])).toBeUndefined();
    expect(buildSrcSet("")).toBeUndefined();
    expect(buildSrcSet([{ width: 100 }])).toBeUndefined();
    expect(buildSrcSet({ not: "an array" })).toBeUndefined();
  });

  it("accepts plain-string entries alongside objects", () => {
    expect(buildSrcSet(["/a.webp", { url: "/b.webp", width: 800 }])).toBe("/a.webp, /b.webp 800w");
  });
});

describe("marketingImageSizes", () => {
  it("is a non-empty sizes expression (required for width-descriptor srcsets)", () => {
    // Without `sizes`, a browser treats a w-descriptor srcset as 100vw and
    // will over-fetch on every split-layout slot.
    expect(typeof marketingImageSizes).toBe("string");
    expect(marketingImageSizes.length).toBeGreaterThan(0);
    expect(marketingImageSizes).toMatch(/vw/);
  });
});
