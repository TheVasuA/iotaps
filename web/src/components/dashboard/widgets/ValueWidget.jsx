import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric, formatValue } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Clean value card — large number, subtle metric label below.
export default function ValueWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;

  const latest = useAppSelector(selectLatest(deviceId));
  const value = readMetric(latest?.data, metric);

  if (!deviceId || !metric) return <UnboundNotice />;

  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <span className="text-2xl font-bold tabular-nums text-foreground">
        {formatValue(value, { precision: config.precision })}
      </span>
      {config.unit && (
        <span className="text-xs font-medium text-muted-foreground">{config.unit}</span>
      )}
    </div>
  );
}
