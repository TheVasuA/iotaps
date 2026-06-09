import { Warning, CheckCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric, evaluateThreshold, formatValue } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Alert badge: a threshold indicator that turns red when breached (Req 7.3).
// Re-evaluates against the device's latest telemetry value (Req 7.4).
export default function AlertBadgeWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;
  const operator = config.operator || ">";
  const threshold = config.threshold;

  const latest = useAppSelector(selectLatest(deviceId));
  const value = readMetric(latest?.data, metric);
  const breached = evaluateThreshold(value, operator, threshold);

  if (!deviceId || !metric) return <UnboundNotice />;

  return (
    <div
      className={cn(
        "flex h-full flex-col items-center justify-center gap-1 rounded-md p-3 text-center transition-colors",
        breached
          ? "bg-destructive/10 text-destructive"
          : "bg-muted/40 text-muted-foreground"
      )}
    >
      {breached ? <Warning size={24} weight="fill" /> : <CheckCircle size={24} />}
      <span className="text-sm font-medium">
        {breached ? "Alert" : "Normal"}
      </span>
      <span className="text-xs tabular-nums">
        {formatValue(value)} {operator} {threshold}
      </span>
    </div>
  );
}
