import { useState, useEffect } from "react";
import { Switch } from "@/components/ui/switch";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Toggle control widget (Req 7.3). Reflects the device's latest state from
// telemetry (Req 7.4) and issues an ON/OFF command through `onCommand`.
// Uses optimistic UI: flips immediately on click, then syncs with telemetry.
export default function ToggleWidget({ widget, onCommand, readOnly }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;

  const latest = useAppSelector(selectLatest(deviceId));
  const value = readMetric(latest?.data, metric);
  const telemetryOn = value != null && value !== 0;

  // Local optimistic state — flips immediately on user action
  const [optimistic, setOptimistic] = useState(null);

  // Sync with telemetry when it arrives (telemetry is source of truth)
  useEffect(() => {
    if (value != null) {
      setOptimistic(null); // clear optimistic, telemetry caught up
    }
  }, [value]);

  const on = optimistic != null ? optimistic : telemetryOn;

  if (!deviceId) return <UnboundNotice />;

  const handle = (next) => {
    if (readOnly) return;
    // Optimistic flip
    setOptimistic(next);
    onCommand?.({
      deviceId,
      command: config.command || metric,
      type: next ? "on" : "off",
      value: next ? 1 : 0,
    });
  };

  return (
    <div className="flex h-full items-center justify-between gap-3 p-4">
      <span className="text-sm text-muted-foreground">{on ? "On" : "Off"}</span>
      <Switch checked={on} onChange={handle} disabled={readOnly} />
    </div>
  );
}
