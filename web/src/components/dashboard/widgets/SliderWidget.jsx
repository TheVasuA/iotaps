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
      command: config.command || metric || "value",
      type: "value",
      value,
    });
  };

  return (
    <div className="flex h-full flex-col justify-center gap-2 p-4">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{min}</span>
        <span className="text-sm font-medium tabular-nums text-foreground">
          {pos}
        </span>
        <span>{max}</span>
      </div>
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
        className="w-full accent-[hsl(var(--primary))]"
      />
    </div>
  );
}
