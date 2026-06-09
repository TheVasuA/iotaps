// Property-based test for the frontend volume-discount pricing mirror
// (Task 14.5, Req 16).
//
// Feature: iotaps-platform, Property 10: Volume discount pricing correctness and monotonicity
//
// Property 10 (design.md "Correctness Properties"):
//
//   For any device count, the resolved monthly per-device price equals the tier
//   rate (1-10 -> ₹99, 11-50 -> ₹79, 51-200 -> ₹69, 201+ -> ₹59), the price is
//   non-increasing as device count grows, the tier boundaries (10/11, 50/51,
//   200/201) are exact, and an annual purchase totals ₹948 per device.
//
// Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7
//
// The pricing functions in src/lib/pricing.js are pure, so each fast-check
// example simply calls them directly and compares against the reference tier
// rate derived straight from the Req 16.2-16.5 bands.

import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  unitPriceMonthly,
  unitPrice,
  total,
  ANNUAL_UNIT_PRICE,
} from "./pricing.js";

// Reference tier rate derived straight from the Req 16.2-16.5 bands.
function expectedMonthlyRate(deviceCount) {
  if (deviceCount <= 10) return 99;
  if (deviceCount <= 50) return 79;
  if (deviceCount <= 200) return 69;
  return 59;
}

describe("Property 10: volume discount pricing correctness and monotonicity", () => {
  it("frontend mirror matches tier rates, is monotonic, and annual = 948/device", () => {
    fc.assert(
      // Device counts span every tier, including the open-ended 201+ band, and
      // stay well above the boundaries so the monotonicity step covers all tiers.
      fc.property(fc.integer({ min: 1, max: 5000 }), (deviceCount) => {
        const rate = unitPriceMonthly(deviceCount);

        // (a) Correctness: the resolved monthly rate equals the tier rate for
        //     the band the device count falls in (Req 16.2-16.5).
        expect(rate).toBe(expectedMonthlyRate(deviceCount));

        // (b) The advertised rate is one of the four published tier rates (Req 16.6).
        expect([99, 79, 69, 59]).toContain(rate);

        // (c) Annual purchases always total ₹948 per device (Req 16.1, 16.7),
        //     independent of the volume tier.
        expect(unitPrice(deviceCount, "yearly")).toBe(ANNUAL_UNIT_PRICE);
        expect(total(deviceCount, "yearly")).toBe(deviceCount * ANNUAL_UNIT_PRICE);

        // (d) Monthly total is the per-device rate times the count (Req 16.6).
        expect(total(deviceCount, "monthly")).toBe(deviceCount * rate);

        // (e) Monotonicity: adding one more device never raises the per-device
        //     monthly price (non-increasing as device_count grows).
        expect(unitPriceMonthly(deviceCount + 1)).toBeLessThanOrEqual(rate);
      }),
      { numRuns: 30 }
    );
  });

  it("per-device monthly price is globally non-increasing (larger fleet never costs more per device)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 5000 }),
        fc.integer({ min: 0, max: 4999 }),
        (smaller, delta) => {
          const larger = smaller + delta;
          expect(unitPriceMonthly(larger)).toBeLessThanOrEqual(
            unitPriceMonthly(smaller)
          );
        }
      ),
      { numRuns: 30 }
    );
  });

  it("tier boundaries (10/11, 50/51, 200/201) step to the next tier exactly", () => {
    // Req 16.6: each volume discount tier applies only within its range.
    expect(unitPriceMonthly(10)).toBe(99);
    expect(unitPriceMonthly(11)).toBe(79);
    expect(unitPriceMonthly(50)).toBe(79);
    expect(unitPriceMonthly(51)).toBe(69);
    expect(unitPriceMonthly(200)).toBe(69);
    expect(unitPriceMonthly(201)).toBe(59);
  });
});
