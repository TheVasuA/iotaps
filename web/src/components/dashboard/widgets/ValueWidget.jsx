import { useMemo } from "react";
import { TrendUp, TrendDown, Minus } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useAppSelector } from "@/store/hooks";
import { selectLatest, selectSeries } from "@/store/dashboardsSlice";
import { readMetric, formatValue } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// KPI value card following common dashboard best practice: a prominent headline
// value with unit, a trend indicator versus the previous reading, a compact
// sparkline for recent context, optional threshold colour guardrails, and a
// freshness line so users can tell how recent the reading is.

/** Short relative-time label, e.g. "just now", "12s ago", "3m ago". */
function relativeTime(ts) {
  if (!ts) return null;
  const secs = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
  if (!Number.isFinite(secs) || secs < 0) return null;
  if (secs < 5) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Tiny inline SVG sparkline of recent values (no chart library overhead). */
function Sparkline({ values }) {
  const path = useMemo(() => {
    if (!values || values.length < 2) return null;
    const w = 100;
    const h = 28;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = w / (values.length - 1);
    const pts = values.map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / range) * h;
      return [x, y];
    });
    const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const area = `${line} L${w},${h} L0,${h} Z`;
    return { line, area };
  }, [values]);

  if (!path) return null;
  return (
    <svg
      viewBox="0 0 100 28"
      preserveAspectRatio="none"
      className="h-7 w-full text-primary"
      aria-hidden="true"
    >
      <path d={path.area} fill="currentColor" opacity="0.12" />
      <path
        d={path.line}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function ValueWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;

  const latest = useAppSelector(selectLatest(deviceId));
  const series = useAppSelector(selectSeries(deviceId, metric));
  const value = readMetric(latest?.data, metric);

  // Trend vs the previous reading (direction + delta), from the live series.
  const { direction, delta } = useMemo(() => {
    if (!series || series.length < 2) return { direction: "flat", delta: null };
    const curr = series[series.length - 1].value;
    const prev = series[series.length - 2].value;
    const d = curr - prev;
    if (Math.abs(d) < 1e-9) return { direction: "flat", delta: 0 };
    return { direction: d > 0 ? "up" : "down", delta: d };
  }, [series]);

  // Optional colour guardrails: amber once outside the configured comfort band.
  const warn = useMemo(() => {
    if (value == null) return false;
    const hi = Number(config.warnAbove);
    const lo = Number(config.warnBelow);
    if (Number.isFinite(hi) && value > hi) return true;
    if (Number.isFinite(lo) && value < lo) return true;
    return false;
  }, [value, config.warnAbove, config.warnBelow]);

  const sparkValues = useMemo(
    () => (series || []).slice(-40).map((p) => p.value),
    [series]
  );

  if (!deviceId || !metric) return <UnboundNotice />;

  const freshness = relativeTime(latest?.ts);
  const TrendIcon = direction === "up" ? TrendUp : direction === "down" ? TrendDown : Minus;
  const trendColor =
    direction === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : direction === "down"
        ? "text-rose-600 dark:text-rose-400"
        : "text-muted-foreground";

  return (
    <div className="flex h-full flex-col justify-center gap-1 px-3 py-2">
      <div className="flex items-baseline gap-1.5">
        <span
          className={cn(
            "text-3xl font-bold leading-none tabular-nums",
            warn ? "text-amber-600 dark:text-amber-400" : "text-foreground"
          )}
        >
          {formatValue(value, { precision: config.precision })}
        </span>
        {config.unit && (
          <span className="text-sm font-medium text-muted-foreground">
            {config.unit}
          </span>
        )}
      </div>

      {delta != null && delta !== 0 && (
        <div className={cn("flex items-center gap-1 text-xs font-medium", trendColor)}>
          <TrendIcon size={13} weight="bold" />
          <span className="tabular-nums">
            {delta > 0 ? "+" : ""}
            {formatValue(delta, { precision: config.precision })}
          </span>
        </div>
      )}

      {sparkValues.length >= 2 && (
        <div className="mt-0.5">
          <Sparkline values={sparkValues} />
        </div>
      )}

      {freshness && (
        <span className="mt-0.5 text-[10px] text-muted-foreground">{freshness}</span>
      )}
    </div>
  );
}
