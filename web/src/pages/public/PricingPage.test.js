// Source-level guards for the public Pricing page's data sourcing (Req 16.1).
// The page renders server pricing (GET /billing/plans) but must fall back to
// the bundled @/lib/pricing mirror when the fetch fails, so a visitor never
// sees a blank price section. No jsdom is used - these assert on the source,
// the same style as src/lib/marketingHeadings.test.js.

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, "PricingPage.jsx"), "utf8");

describe("PricingPage data sourcing", () => {
  it("fetches plans through the public (unauthenticated) path", () => {
    expect(source).toMatch(/import \{ getPublicPlans \} from "@\/lib\/publicApi"/);
    expect(source).toMatch(/getPublicPlans\(\)/);
  });

  it("seeds prices from the @/lib/pricing fallback constants", () => {
    // Initial state is the bundled mirror; a successful fetch replaces it and
    // a failed one leaves it in place.
    expect(source).toMatch(/annualUnitPrice: ANNUAL_UNIT_PRICE/);
    expect(source).toMatch(/tiers: PRICING_TIERS/);
    expect(source).toMatch(/from "@\/lib\/pricing"/);
  });

  it("keeps the volume-pricing table driven by the tier list", () => {
    expect(source).toMatch(/\{tiers\.map\(/);
    expect(source).toMatch(/tier\.unitPriceMonthly/);
  });

  it("advertises the ENTRY tier as 'from', not the volume floor", () => {
    // The 201+ band is the cheapest rate a fleet can reach, not the price one
    // device starts at. Anchoring "from" on tiers[0] keeps the card and the
    // meta description ("Pro from ₹99/device/mo with volume discounts down to
    // ₹59") saying the same thing.
    expect(source).toMatch(/entryPriceMonthly = tiers\[0\]\.unitPriceMonthly/);
    expect(source).toMatch(/floorPriceMonthly = tiers\[tiers\.length - 1\]\.unitPriceMonthly/);
    expect(source).not.toMatch(/from ₹\$\{floorPriceMonthly\}/);
  });
});
