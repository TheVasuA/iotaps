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
    <div className="flex h-full items-center justify-between px-3 select-none">
      <div className="flex flex-col justify-center">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              breached ? "bg-rose-500 animate-ping" : "bg-emerald-500"
            )}
          />
          <span className={cn("text-sm font-bold tracking-tight", breached ? "text-rose-600" : "text-slate-800 dark:text-slate-100")}>
            {breached ? "Threshold Breached" : "System Nominal"}
          </span>
        </div>
        <span className="mt-1 text-[11px] font-mono text-slate-400">
          {formatValue(value)} {operator} {threshold}
        </span>
      </div>
      <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", breached ? "bg-rose-50 border-rose-100 text-rose-600" : "bg-slate-50 dark:bg-slate-800/60 border-slate-100 dark:border-slate-800 text-slate-400")}>
        {breached ? <Warning size={18} weight="bold" /> : <CheckCircle size={18} weight="regular" />}
      </div>
    </div>
  );
}
