// Frontend volume-discount pricing mirror (Task 14.5, Req 16).
//
// Single source of truth for the billing UI's pricing math. This mirrors the
// backend engine in app/services/billing_service.py so the quote shown in the
// SPA matches what the API charges:
//
//   unitPriceMonthly(deviceCount):
//     1-10   -> ₹99
//     11-50  -> ₹79
//     51-200 -> ₹69
//     201+   -> ₹59
//   annual: a fixed ₹948 per device per year (Req 16.1, 16.7).
//
// The tier applies to the whole purchase based on its device-count band; the
// boundaries (10/11, 50/51, 200/201) are exact (Req 16.6). Per-device monthly
// price is non-increasing as the device count grows (Property 10).
//
// All amounts are whole rupees (integers) - the published prices have no
// sub-rupee component, so there is no rounding to reason about.

export const CYCLE_MONTHLY = "monthly";
export const CYCLE_YEARLY = "yearly";

// Fixed annual price per device (Req 16.1, 16.7).
export const ANNUAL_UNIT_PRICE = 948;

// Ordered from the smallest band to the open-ended top tier (Req 16.2-16.5).
// `maxDevices: null` denotes the open-ended 201+ band. Order matters:
// `unitPriceMonthly` walks these and returns the first matching tier.
export const PRICING_TIERS = [
  { minDevices: 1, maxDevices: 10, unitPriceMonthly: 99 },
  { minDevices: 11, maxDevices: 50, unitPriceMonthly: 79 },
  { minDevices: 51, maxDevices: 200, unitPriceMonthly: 69 },
  { minDevices: 201, maxDevices: null, unitPriceMonthly: 59 },
];

function validateDeviceCount(deviceCount) {
  if (
    typeof deviceCount !== "number" ||
    !Number.isInteger(deviceCount) ||
    deviceCount < 1
  ) {
    throw new Error("deviceCount must be an integer >= 1");
  }
  return deviceCount;
}

// Resolve a billing-cycle string to "monthly"/"yearly" (case-insensitive).
export function normalizeCycle(billingCycle) {
  if (typeof billingCycle === "string") {
    const normalized = billingCycle.trim().toLowerCase();
    if (normalized === CYCLE_MONTHLY || normalized === CYCLE_YEARLY) {
      return normalized;
    }
  }
  throw new Error("billingCycle must be 'monthly' or 'yearly'");
}

// Per-device monthly price for a purchase of `deviceCount` devices: the rate
// for the volume tier the count falls in (Req 16.2-16.5); boundaries are exact.
export function unitPriceMonthly(deviceCount) {
  validateDeviceCount(deviceCount);
  for (const tier of PRICING_TIERS) {
    if (tier.maxDevices === null || deviceCount <= tier.maxDevices) {
      return tier.unitPriceMonthly;
    }
  }
  // Unreachable: the final tier is open-ended, but keep a defensive default.
  return PRICING_TIERS[PRICING_TIERS.length - 1].unitPriceMonthly;
}

// Per-device price for the given cycle. Yearly is the fixed ₹948/device
// (Req 16.1, 16.7); monthly uses the volume tier rate (Req 16.2-16.5).
export function unitPrice(deviceCount, billingCycle) {
  const cycle = normalizeCycle(billingCycle);
  validateDeviceCount(deviceCount);
  if (cycle === CYCLE_YEARLY) {
    return ANNUAL_UNIT_PRICE;
  }
  return unitPriceMonthly(deviceCount);
}

// Total purchase price = per-device price x device count (Req 16.6, 16.7).
export function total(deviceCount, billingCycle) {
  validateDeviceCount(deviceCount);
  return deviceCount * unitPrice(deviceCount, billingCycle);
}

// Build a pricing quote, mirroring the backend POST /billing/quote shape
// ({ deviceCount, billingCycle, unitPrice, total }) so the UI and API agree.
export function quote(deviceCount, billingCycle) {
  const cycle = normalizeCycle(billingCycle);
  validateDeviceCount(deviceCount);
  const perDevice = unitPrice(deviceCount, cycle);
  return {
    deviceCount,
    billingCycle: cycle,
    unitPrice: perDevice,
    total: deviceCount * perDevice,
  };
}
