import { useMemo, useState, useEffect } from "react";
import ReactECharts from "echarts-for-react";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric } from "@/lib/widgets";
import { getChartTheme } from "@/lib/chartTheme";
import { UnboundNotice } from "./ChartWidget";

function getThemeColors() {
  const { foreground, muted, border } = getChartTheme();
  return { foreground, muted, border };
}

const DEFAULT_ZONES = [
  { pct: 0.4, color: "#22c55e" },
  { pct: 0.7, color: "#eab308" },
  { pct: 1.0, color: "#ef4444" },
];

function parseZones(config, min, max) {
  if (Array.isArray(config.zones) && config.zones.length > 0) {
    const range = max - min || 1;
    return config.zones.map((z) => ({
      pct: Math.min((Number(z.value) - min) / range, 1),
      color: z.color || "#3b82f6",
    }));
  }
  return DEFAULT_ZONES;
}

function getActiveColor(value, zones, min, max) {
  if (value == null) return zones[0]?.color || "#3b82f6";
  const range = max - min || 1;
  const pct = (value - min) / range;
  for (const zone of zones) {
    if (pct <= zone.pct) return zone.color;
  }
  return zones[zones.length - 1]?.color || "#ef4444";
}

function formatNumber(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  if (abs >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return v % 1 === 0 ? v.toString() : v.toFixed(1);
}

export default function GaugeWidget({ widget }) {
  const config = widget.config || {};
  const deviceId = config.deviceId;
  const metric = config.metric;
  const min = Number(config.min) || 0;
  const max = Number(config.max) || 100;
  const unit = config.unit || "";

  const latest = useAppSelector(selectLatest(deviceId));
  const value = readMetric(latest?.data, metric);

  // Startup animation: sweep to max then settle to actual value
  const [animPhase, setAnimPhase] = useState(0); // 0=start, 1=max, 2=settled

  useEffect(() => {
    const t1 = setTimeout(() => setAnimPhase(1), 100); // swing to max
    const t2 = setTimeout(() => setAnimPhase(2), 900); // settle to value
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  let displayValue;
  if (animPhase === 0) displayValue = min;
  else if (animPhase === 1) displayValue = max;
  else displayValue = value == null ? min : value;

  const option = useMemo(() => {
    const colors = getThemeColors();
    const zones = parseZones(config, min, max);
    const activeColor = getActiveColor(displayValue, zones, min, max);

    // Background arc shows zone colors at low opacity
    const zoneColors = zones.map((z) => [z.pct, z.color + "33"]);
    // Ensure last stop is exactly 1
    if (zoneColors.length > 0) zoneColors[zoneColors.length - 1][0] = 1;

    return {
      series: [
        {
          type: "gauge",
          min,
          max,
          splitNumber: 10,
          radius: "82%",
          center: ["50%", "58%"],
          startAngle: 225,
          endAngle: -45,
          progress: {
            show: true,
            width: 12,
            roundCap: true,
            itemStyle: { color: activeColor },
          },
          axisLine: {
            lineStyle: {
              width: 12,
              color: zoneColors,
            },
            roundCap: true,
          },
          axisTick: {
            show: true,
            splitNumber: 5,
            distance: -2,
            length: 4,
            lineStyle: { color: colors.muted, width: 1 },
          },
          splitLine: {
            show: true,
            distance: -2,
            length: 10,
            lineStyle: { color: colors.muted, width: 2 },
          },
          axisLabel: {
            show: true,
            distance: -26,
            fontSize: 9,
            color: colors.muted,
            formatter: (v) => formatNumber(v),
          },
          pointer: {
            show: true,
            length: "55%",
            width: 5,
            icon: "triangle",
            itemStyle: {
              color: activeColor,
            },
          },
          anchor: {
            show: true,
            size: 8,
            showAbove: true,
            itemStyle: {
              color: colors.foreground,
              borderColor: colors.border,
              borderWidth: 2,
            },
          },
          title: {
            show: true,
            offsetCenter: [0, "80%"],
            fontSize: 10,
            color: colors.muted,
          },
          detail: {
            valueAnimation: true,
            formatter: (v) => (value == null ? "—" : formatNumber(v)),
            fontSize: 22,
            fontWeight: 700,
            color: activeColor,
            offsetCenter: [0, "55%"],
          },
          data: [{ value: displayValue, name: unit || "" }],
        },
      ],
    };
  }, [value, min, max, unit, metric, config, displayValue]);

  if (!deviceId || !metric) return <UnboundNotice />;

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
