import { useEffect, useState } from "react";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Slider control widget (Req 7.3). Tracks the device's latest value from
// telemetry (Req 7.4) and publishes the chosen value via `onCommand` on
// release (commit on pointer-up to avoid flooding the command topic). The
// command transport is provided by task 9.3.
export default function SliderWidget({ widget, onCommand, readOnly }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;
  const min = Number(config.min) || 0;
  const max = Number(config.max) || 255;
  const step = Number(config.step) || 1;

  const latest = useAppSelector(selectLatest(deviceId));
  const remoteValue = readMetric(latest?.data, metric);

  // Local position lets the thumb move smoothly; it re-syncs to telemetry when
  // the device reports a new value and the user is not currently dragging.
  const [pos, setPos] = useState(remoteValue ?? min);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!dragging && remoteValue != null) setPos(remoteValue);
  }, [remoteValue, dragging]);

  if (!deviceId) return <UnboundNotice />;

  const commit = (value) => {
    if (readOnly) return;
    onCommand?.({
      deviceId,
      command: config.command || metric,
      type: "value",
      value,
    });
  };

  const pct = Math.min(100, Math.max(0, ((pos - min) / (max - min || 1)) * 100));

  return (
    <div className="flex h-full flex-col justify-center px-4 py-2 select-none">
      <div className="flex items-baseline justify-between mb-1.5">
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
            {pos}
          </span>
          {config.unit ? (
            <span className="text-[11px] font-medium text-slate-400 uppercase">{config.unit}</span>
          ) : null}
        </div>
        <span className="text-[10px] font-mono text-slate-400">
          {Math.round(pct)}%
        </span>
      </div>

      <div className="relative flex items-center h-4">
        <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 relative overflow-hidden">
          <div
            className="h-full rounded-full bg-slate-900 dark:bg-slate-100 transition-all duration-75"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div
          className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-xs border border-slate-300 dark:border-slate-600 transition-transform"
          style={{ left: `${pct}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={pos}
          disabled={readOnly}
          aria-label={config.title || metric || "slider"}
          onChange={(e) => {
            setDragging(true);
            setPos(Number(e.target.value));
          }}
          onMouseUp={(e) => {
            setDragging(false);
            commit(Number(e.target.value));
          }}
          onTouchEnd={(e) => {
            setDragging(false);
            commit(Number(e.target.value));
          }}
          onKeyUp={(e) => {
            setDragging(false);
            commit(Number(e.target.value));
          }}
          className="absolute inset-0 opacity-0 cursor-pointer"
        />
      </div>

      <div className="flex items-center justify-between text-[9px] font-mono text-slate-300 dark:text-slate-600 px-0.5 pt-1 leading-none">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
