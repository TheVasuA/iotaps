// Unit + property tests for the dashboard widget data-binding helpers
// (Task 8.2, Req 7.3, 7.4, 7.7). These functions are pure, so they are
// exercised directly.

import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  WIDGET_TYPES,
  isWidgetType,
  widgetMeta,
  defaultConfigFor,
  defaultLayoutFor,
  readMetric,
  evaluateThreshold,
  appendPoint,
  downsampleSeries,
  formatValue,
} from "./widgets.js";

describe("widget catalog", () => {
  it("exposes the 8 design widget types", () => {
    expect(WIDGET_TYPES).toEqual([
      "line",
      "gauge",
      "bar",
      "value",
      "map",
      "toggle",
      "slider",
      "alert_badge",
    ]);
  });

  it("every type has catalog metadata with a default layout and config", () => {
    for (const type of WIDGET_TYPES) {
      const meta = widgetMeta(type);
      expect(meta).toBeTruthy();
      expect(meta.defaultLayout.w).toBeGreaterThan(0);
      expect(meta.defaultLayout.h).toBeGreaterThan(0);
      expect(typeof meta.defaultConfig).toBe("object");
    }
  });

  it("isWidgetType rejects unknown types", () => {
    expect(isWidgetType("line")).toBe(true);
    expect(isWidgetType("bogus")).toBe(false);
  });

  it("defaultConfigFor returns a fresh object merged with overrides", () => {
    const a = defaultConfigFor("gauge");
    const b = defaultConfigFor("gauge", { max: 200 });
    a.min = 999;
    expect(b.min).toBe(0); // not aliased
    expect(b.max).toBe(200);
  });

  it("defaultLayoutFor sets the grid item id and type-default size", () => {
    const l = defaultLayoutFor("value", "w1");
    expect(l.i).toBe("w1");
    expect(l.w).toBe(widgetMeta("value").defaultLayout.w);
  });
});

describe("readMetric", () => {
  it("reads numeric values", () => {
    expect(readMetric({ temp: 22.5 }, "temp")).toBe(22.5);
  });
  it("coerces numeric strings and booleans", () => {
    expect(readMetric({ t: "22.5" }, "t")).toBe(22.5);
    expect(readMetric({ on: true }, "on")).toBe(1);
    expect(readMetric({ on: false }, "on")).toBe(0);
  });
  it("returns null for missing / non-numeric / bad input", () => {
    expect(readMetric({ temp: 1 }, "humidity")).toBeNull();
    expect(readMetric({ t: "abc" }, "t")).toBeNull();
    expect(readMetric(null, "t")).toBeNull();
    expect(readMetric({ t: 1 }, "")).toBeNull();
  });
});

describe("evaluateThreshold", () => {
  it("evaluates each operator", () => {
    expect(evaluateThreshold(5, ">", 3)).toBe(true);
    expect(evaluateThreshold(5, ">=", 5)).toBe(true);
    expect(evaluateThreshold(2, "<", 3)).toBe(true);
    expect(evaluateThreshold(3, "<=", 3)).toBe(true);
    expect(evaluateThreshold(3, "==", 3)).toBe(true);
    expect(evaluateThreshold(3, "!=", 4)).toBe(true);
  });
  it("returns false for null value or unknown operator", () => {
    expect(evaluateThreshold(null, ">", 3)).toBe(false);
    expect(evaluateThreshold(5, "??", 3)).toBe(false);
  });
});

describe("appendPoint", () => {
  it("appends and bounds the ring buffer to maxPoints", () => {
    let s = [];
    for (let i = 0; i < 10; i += 1) {
      s = appendPoint(s, { ts: i, value: i }, 5);
    }
    expect(s).toHaveLength(5);
    expect(s[0].value).toBe(5);
    expect(s[4].value).toBe(9);
  });
  it("ignores points with a null/non-finite value", () => {
    const s = appendPoint([{ ts: 0, value: 1 }], { ts: 1, value: null }, 10);
    expect(s).toHaveLength(1);
  });
  it("does not mutate the input array", () => {
    const orig = [{ ts: 0, value: 1 }];
    const next = appendPoint(orig, { ts: 1, value: 2 }, 10);
    expect(orig).toHaveLength(1);
    expect(next).toHaveLength(2);
  });
});

describe("formatValue", () => {
  it("applies precision and unit", () => {
    expect(formatValue(22.456, { precision: 1, unit: "°C" })).toBe("22.5 °C");
  });
  it("renders an em dash for null", () => {
    expect(formatValue(null)).toBe("—");
  });
});

describe("downsampleSeries", () => {
  it("returns the input unchanged when it already fits", () => {
    const s = [
      { ts: 0, value: 1 },
      { ts: 1, value: 2 },
    ];
    expect(downsampleSeries(s, 500)).toBe(s);
  });

  it("reduces a large series well below the input size", () => {
    const s = Array.from({ length: 10000 }, (_, i) => ({
      ts: i,
      value: Math.sin(i / 10),
    }));
    const out = downsampleSeries(s, 500);
    // Envelope downsampling emits up to 2 points (min+max) per bucket plus the
    // two endpoints, so the bound is 2*maxPoints, far below the 10k input.
    expect(out.length).toBeLessThanOrEqual(1000);
    expect(out.length).toBeLessThan(s.length);
    expect(out.length).toBeGreaterThan(2);
  });

  it("always preserves the first and last points (exact time axis, Req 7.7)", () => {
    const s = Array.from({ length: 5000 }, (_, i) => ({ ts: i, value: i }));
    const out = downsampleSeries(s, 200);
    expect(out[0]).toEqual(s[0]);
    expect(out[out.length - 1]).toEqual(s[s.length - 1]);
  });
});

describe("downsampleSeries virtualization invariants (Req 7.7)", () => {
  it("never grows the series, bounds the output, preserves endpoints, keeps time order, and preserves the value envelope", () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: -1000, max: 1000 }), {
          minLength: 0,
          maxLength: 4000,
        }),
        fc.integer({ min: 3, max: 600 }),
        (values, maxPoints) => {
          // Build a strictly time-increasing series from the random values.
          const series = values.map((v, i) => ({ ts: i, value: v }));
          const out = downsampleSeries(series, maxPoints);

          // (a) Never produces more points than the input.
          expect(out.length).toBeLessThanOrEqual(series.length);

          if (series.length <= maxPoints) {
            // Below the threshold the series is returned untouched.
            expect(out).toBe(series);
            return;
          }

          // (b) Output is bounded for large inputs. Each interior bucket can
          //     emit up to 2 points (min + max) plus the two endpoints.
          expect(out.length).toBeLessThanOrEqual(2 * maxPoints);

          // (c) Endpoints are preserved exactly so the x-range is exact.
          expect(out[0]).toEqual(series[0]);
          expect(out[out.length - 1]).toEqual(series[series.length - 1]);

          // (d) Time axis stays monotonically non-decreasing.
          for (let i = 1; i < out.length; i += 1) {
            expect(out[i].ts).toBeGreaterThanOrEqual(out[i - 1].ts);
          }

          // (e) Envelope preserved: the global min and max values both survive
          //     downsampling (spikes are not lost).
          const inMin = Math.min(...series.map((p) => p.value));
          const inMax = Math.max(...series.map((p) => p.value));
          const outMin = Math.min(...out.map((p) => p.value));
          const outMax = Math.max(...out.map((p) => p.value));
          expect(outMin).toBe(inMin);
          expect(outMax).toBe(inMax);

          // (f) Every emitted point comes from the input series.
          const inputSet = new Set(series.map((p) => `${p.ts}:${p.value}`));
          for (const p of out) {
            expect(inputSet.has(`${p.ts}:${p.value}`)).toBe(true);
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});
