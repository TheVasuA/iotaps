import { Switch } from "@/components/ui/switch";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Toggle control widget (Req 7.3). Reflects the device's latest state from
// telemetry (Req 7.4) and issues an ON/OFF command through `onCommand`. The
// command transport (POST /devices/{id}/commands + Sonner ACK feedback) is
// wired in task 9.3; this widget is transport-agnostic so it composes with it.
export default function ToggleWidget({ widget, onCommand, readOnly }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;

  const latest = useAppSelector(selectLatest(deviceId));
  const value = readMetric(latest?.data, metric);
  const on = value != null && value !== 0;

  if (!deviceId) return <UnboundNotice />;

  const handle = (next) => {
    if (readOnly) return;
    onCommand?.({
      deviceId,
      command: config.command || metric || "toggle",
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
