// Widget catalog and pure data-binding helpers for the dashboard canvas
// (Task 8.2, Req 7).
//
// This module is deliberately free of React so the binding / virtualization
// logic can be unit-tested in isolation. The 8 widget types from design.md
// ("widgets.type = line/gauge/bar/value/map/toggle/slider/alert_badge") are
// described here as metadata; the React renderers in components/dashboard live
// on top of this catalog.

// The 8 supported widget types (design.md widgets table; Req 7.3).
export const WIDGET_TYPES = [
  "line",
  "gauge",
  "bar",
  "value",
  "map",
  "toggle",
  "slider",
  "alert_badge",
];

// Display metadata + sensible default grid size (React Grid Layout units) and
// default config per type. `category` distinguishes read-only visualizations
// from interactive control widgets (toggle/slider issue device commands).
export const WIDGET_CATALOG = {
  line: {
    type: "line",
    label: "Line chart",
    description: "Time-series line chart with large-series virtualization.",
    category: "chart",
    defaultLayout: { w: 6, h: 4, minW: 3, minH: 3 },
    defaultConfig: { metric: "", title: "Line chart", maxPoints: 500 },
  },
  bar: {
    type: "bar",
    label: "Bar chart",
    description: "Bar chart of recent telemetry samples.",
    category: "chart",
    defaultLayout: { w: 6, h: 4, minW: 3, minH: 3 },
    defaultConfig: { metric: "", title: "Bar chart", maxPoints: 500 },
  },
  gauge: {
    type: "gauge",
    label: "Gauge",
    description: "Radial gauge for a single metric against a range.",
    category: "chart",
    defaultLayout: { w: 3, h: 4, minW: 2, minH: 3 },
    defaultConfig: { metric: "", title: "Gauge", min: 0, max: 100, unit: "" },
  },
  value: {
    type: "value",
    label: "Value card",
    description: "Latest value of a single metric.",
    category: "value",
    defaultLayout: { w: 3, h: 2, minW: 2, minH: 2 },
    defaultConfig: { metric: "", title: "Value", unit: "", precision: 1 },
  },
  map: {
    type: "map",
    label: "Map",
    description: "Plots the device's latest latitude/longitude.",
    category: "value",
    defaultLayout: { w: 4, h: 4, minW: 3, minH: 3 },
    defaultConfig: { latMetric: "lat", lonMetric: "lon", title: "Location" },
  },
  toggle: {
    type: "toggle",
    label: "Toggle",
    description: "ON/OFF control bound to a device command.",
    category: "control",
    defaultLayout: { w: 3, h: 2, minW: 2, minH: 2 },
    defaultConfig: { metric: "", title: "Toggle", command: "" },
  },
  slider: {
    type: "slider",
    label: "Slider",
    description: "Value control bound to a device command.",
    category: "control",
    defaultLayout: { w: 4, h: 2, minW: 3, minH: 2 },
    defaultConfig: {
      metric: "",
      title: "Slider",
      command: "",
      min: 0,
      max: 255,
      step: 1,
    },
  },
  alert_badge: {
    type: "alert_badge",
    label: "Alert badge",
    description: "Threshold indicator that turns red when breached.",
    category: "value",
    defaultLayout: { w: 3, h: 2, minW: 2, minH: 2 },
    defaultConfig: {
      metric: "",
      title: "Alert",
      operator: ">",
      threshold: 0,
    },
  },
};

/** Whether `type` is one of the supported widget types. */
export function isWidgetType(type) {
  return WIDGET_TYPES.includes(type);
}

/** Catalog entry for a type, or undefined. */
export function widgetMeta(type) {
  return WIDGET_CATALOG[type];
}

/**
 * Build the default config for a new widget of `type`, merged with any
 * overrides. Returns a fresh object (never shares references with the catalog).
 */
export function defaultConfigFor(type, overrides = {}) {
  const meta = WIDGET_CATALOG[type];
  if (!meta) return { ...overrides };
  return { ...meta.defaultConfig, ...overrides };
}

/**
 * Default React Grid Layout item for a new widget. `id` becomes the layout `i`.
 * `position` may supply x/y; otherwise the item is placed at the origin and RGL
 * compaction finds a slot.
 */
export function defaultLayoutFor(type, id, position = {}) {
  const meta = WIDGET_CATALOG[type] || { defaultLayout: { w: 4, h: 3 } };
  const { w, h, minW, minH } = meta.defaultLayout;
  return {
    i: id,
    x: position.x ?? 0,
    y: position.y ?? Infinity, // Infinity => append to the bottom (RGL idiom).
    w,
    h,
    ...(minW != null ? { minW } : {}),
    ...(minH != null ? { minH } : {}),
  };
}

/**
 * Extract a numeric metric value from a telemetry data object.
 *
 * Telemetry frames carry `{data: {temp: 22.5, ...}}`. Returns the numeric
 * value for `metric`, or null when absent / non-numeric. Numeric strings (e.g.
 * "22.5") are coerced so device payloads that stringify numbers still bind.
 */
export function readMetric(data, metric) {
  if (!data || !metric) return null;
  const raw = data[metric];
  if (raw == null) return null;
  if (typeof raw === "number") return Number.isFinite(raw) ? raw : null;
  if (typeof raw === "string" && raw.trim() !== "") {
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof raw === "boolean") return raw ? 1 : 0;
  return null;
}

/**
 * Evaluate an alert-badge condition. `operator` is one of >, >=, <, <=, ==, !=.
 * Returns false when the value is null/unknown so a missing metric never shows
 * a false alarm.
 */
export function evaluateThreshold(value, operator, threshold) {
  if (value == null || !Number.isFinite(value)) return false;
  const t = Number(threshold);
  if (!Number.isFinite(t)) return false;
  switch (operator) {
    case ">":
      return value > t;
    case ">=":
      return value >= t;
    case "<":
      return value < t;
    case "<=":
      return value <= t;
    case "==":
      return value === t;
    case "!=":
      return value !== t;
    default:
      return false;
  }
}

/**
 * Append a new telemetry point to a bounded ring buffer used by chart widgets.
 *
 * Keeps at most `maxPoints` samples, dropping the oldest so memory stays bound
 * regardless of stream duration (the in-memory half of Req 7.7 virtualization).
 * Returns a new array (never mutates `series`). Points with a null value are
 * ignored so gaps don't poison the chart.
 */
export function appendPoint(series, point, maxPoints = 500) {
  const list = Array.isArray(series) ? series : [];
  if (!point || point.value == null || !Number.isFinite(point.value)) {
    return list;
  }
  const next = list.length >= maxPoints ? list.slice(list.length - maxPoints + 1) : list.slice();
  next.push(point);
  return next;
}

/**
 * Virtualize a large telemetry series for rendering (Req 7.7).
 *
 * ECharts stays responsive into the low thousands of points, but rendering tens
 * of thousands of DOM-adjacent symbols stalls the UI. When `series` exceeds
 * `maxPoints`, this performs min/max-preserving bucket downsampling (LTTB-style
 * envelope): the series is split into `maxPoints` contiguous buckets and each
 * bucket contributes the points with its min and max value, preserving spikes
 * and the visual envelope while bounding the point count. The first and last
 * points are always retained so the time axis is exact.
 *
 * Returns the input unchanged when it already fits. Input order is preserved.
 */
export function downsampleSeries(series, maxPoints = 500) {
  const list = Array.isArray(series) ? series : [];
  if (maxPoints <= 2 || list.length <= maxPoints) return list;

  const bucketCount = maxPoints;
  const out = [];
  out.push(list[0]);

  // Distribute the interior points across (bucketCount - 2) buckets.
  const interiorStart = 1;
  const interiorEnd = list.length - 1; // exclusive
  const interiorLen = interiorEnd - interiorStart;
  const buckets = bucketCount - 2;
  const bucketSize = interiorLen / buckets;

  for (let b = 0; b < buckets; b += 1) {
    const start = interiorStart + Math.floor(b * bucketSize);
    const end = interiorStart + Math.floor((b + 1) * bucketSize);
    if (end <= start) continue;
    let minIdx = start;
    let maxIdx = start;
    for (let i = start; i < end; i += 1) {
      if (list[i].value < list[minIdx].value) minIdx = i;
      if (list[i].value > list[maxIdx].value) maxIdx = i;
    }
    // Emit min then max in chronological order to keep the time axis monotonic.
    const lo = Math.min(minIdx, maxIdx);
    const hi = Math.max(minIdx, maxIdx);
    out.push(list[lo]);
    if (hi !== lo) out.push(list[hi]);
  }

  out.push(list[list.length - 1]);
  return out;
}

/**
 * Format a numeric value for display, honoring an optional precision and unit.
 * Null/unknown values render as an em dash.
 */
export function formatValue(value, { precision, unit } = {}) {
  if (value == null || !Number.isFinite(value)) return "—";
  const p = Number.isInteger(precision) ? precision : undefined;
  const text = p != null ? value.toFixed(p) : String(value);
  return unit ? `${text} ${unit}` : text;
}
