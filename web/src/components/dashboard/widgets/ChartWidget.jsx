import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useAppSelector } from "@/store/hooks";
import { selectSeries } from "@/store/dashboardsSlice";
import { downsampleSeries } from "@/lib/widgets";

// Professional line/bar chart — minimal grid padding, gradient fill, smooth line.
export default function ChartWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;
  const maxPoints = Number(config.maxPoints) || 500;

  const series = useAppSelector(selectSeries(deviceId, metric));

  const option = useMemo(() => {
    const points = downsampleSeries(series, maxPoints);
    const data = points.map((p) => [p.ts, p.value]);
    const isBar = widget.type === "bar";

    return {
      grid: { top: 8, right: 8, bottom: 20, left: 32 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "#e5e7eb",
        textStyle: { fontSize: 11, color: "#374151" },
      },
      xAxis: {
        type: "time",
        boundaryGap: isBar,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 9, color: "#9ca3af" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 9, color: "#9ca3af" },
        splitLine: { lineStyle: { color: "#f3f4f6", type: "dashed" } },
      },
      series: [
        {
          name: metric || "value",
          type: isBar ? "bar" : "line",
          showSymbol: false,
          smooth: true,
          large: true,
          largeThreshold: 200,
          sampling: "lttb",
          data,
          lineStyle: { width: 2, color: "#3b82f6" },
          itemStyle: { color: "#3b82f6" },
          areaStyle: isBar
            ? undefined
            : {
                color: {
                  type: "linear",
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: "rgba(59,130,246,0.25)" },
                    { offset: 1, color: "rgba(59,130,246,0.02)" },
                  ],
                },
              },
        },
      ],
    };
  }, [series, maxPoints, widget.type, metric]);

  if (!deviceId || !metric) {
    return <UnboundNotice />;
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      lazyUpdate
      style={{ height: "100%", width: "100%" }}
      opts={{ renderer: "canvas" }}
    />
  );
}

export function UnboundNotice() {
  return (
    <div className="flex h-full items-center justify-center text-center text-[11px] text-muted-foreground">
      Tap settings to bind a device + metric
    </div>
  );
}
