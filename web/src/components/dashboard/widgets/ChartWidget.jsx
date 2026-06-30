import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useAppSelector } from "@/store/hooks";
import { selectSeries } from "@/store/dashboardsSlice";
import { downsampleSeries } from "@/lib/widgets";
import { getChartTheme } from "@/lib/chartTheme";

// Professional line/bar chart — minimal grid padding, gradient fill, smooth
// line, and fully theme-aware colours (role theme + light/dark mode).
export default function ChartWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;
  const maxPoints = Number(config.maxPoints) || 500;

  const series = useAppSelector(selectSeries(deviceId, metric));

  const option = useMemo(() => {
    const theme = getChartTheme();
    const points = downsampleSeries(series, maxPoints);
    const data = points.map((p) => [p.ts, p.value]);
    const isBar = widget.type === "bar";

    return {
      grid: { top: 8, right: 8, bottom: 20, left: 32 },
      tooltip: {
        trigger: "axis",
        backgroundColor: theme.card,
        borderColor: theme.border,
        textStyle: { fontSize: 11, color: theme.foreground },
      },
      xAxis: {
        type: "time",
        boundaryGap: isBar,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 9, color: theme.muted },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { fontSize: 9, color: theme.muted },
        splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
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
          itemStyle: { color: theme.primary, borderRadius: isBar ? [3, 3, 0, 0] : 0 },
          lineStyle: { width: 2, color: theme.primary },
          areaStyle: isBar
            ? undefined
            : {
                color: {
                  type: "linear",
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: theme.areaTop },
                    { offset: 1, color: theme.areaBottom },
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

  if (series.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-center text-[11px] text-muted-foreground">
        Waiting for data…
      </div>
    );
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
