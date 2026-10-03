import { useEffect, useState, useMemo } from "react";
import { Copy, GearSix, Trash, ArrowsClockwise, DotsSixVertical } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useAppSelector } from "@/store/hooks";
import { selectLatest, selectSeries } from "@/store/dashboardsSlice";
import { selectDevices, selectDevicesStatus } from "@/store/devicesSlice";
import { readMetric, widgetMeta } from "@/lib/widgets";
import WidgetPalettePreview from "./WidgetPalettePreview";
import DeviceTableWidget from "./widgets/DeviceTableWidget";

function mixColor(from, to, amount) {
  const parse = (hex) => {
    const raw = String(hex || "").replace("#", "");
    if (raw.length !== 6) return [255, 255, 255];
    return [0, 2, 4].map((index) => parseInt(raw.slice(index, index + 2), 16));
  };
  const a = parse(from);
  const b = parse(to);
  const mixed = a.map((channel, index) => Math.round(channel + (b[index] - channel) * amount));
  return `rgb(${mixed.join(",")})`;
}

const KIND_BY_TYPE = {
  toggle: "switch",
  slider: "slider",
  value: "label",
  gauge: "label",
  line: "line_dual",
  bar: "hbar",
  map: "geomap",
  alert_badge: "events",
};

export default function WidgetCard({
  widget,
  editing,
  onCommand,
  onConfigure,
  onDelete,
  onDuplicate,
  onRotate,
  readOnly,
}) {
  const config = widget.config || {};
  const meta = widgetMeta(widget.type);
  const title = config.label || config.title || meta?.label || widget.type || "Widget";
  const hideTitle = Boolean(config.hideTitle);
  const showLabels = config.showLabels !== false;
  const kind = config.variant || KIND_BY_TYPE[widget.type] || "label";
  const deviceId = config.deviceId;
  const metric = config.metric;
  const latest = useAppSelector(selectLatest(deviceId));
  const series = useAppSelector(selectSeries(deviceId, metric));
  const live = deviceId ? readMetric(latest?.data, metric) : null;
  const points = (series || []).slice(-24).map((point) => point.value);
  const [optimistic, setOptimistic] = useState(null);

  useEffect(() => {
    if (live != null) setOptimistic(null);
  }, [live]);

  const shown = optimistic != null ? optimistic : live;
  const switchedOn = shown != null && shown !== 0;
  const devices = useAppSelector(selectDevices);
  const devicesStatus = useAppSelector(selectDevicesStatus);
  const scopedDevices =
    config.deviceScope === "group" && config.groupId
      ? devices.filter((device) => String(device.group_id) === String(config.groupId))
      : devices;
  const fleetReady = devicesStatus === "succeeded" || devices.length > 0;
  const tileFigure =
    kind === "count"
      ? fleetReady
        ? String(scopedDevices.length)
        : "—"
      : kind === "online"
        ? fleetReady
          ? String(scopedDevices.filter((device) => device.status === "online").length)
          : "—"
        : kind === "label"
          ? shown == null
            ? "—"
            : undefined
          : undefined;
  const levelMin = Number(config.levelMin ?? 0);
  const levelMax = Number(config.levelMax ?? 100);
  const levelValue = Number(tileFigure != null && tileFigure !== "—" ? tileFigure : shown);
  const levelPct = Number.isFinite(levelValue)
    ? Math.min(100, Math.max(0, ((levelValue - levelMin) / (levelMax - levelMin || 1)) * 100))
    : 0;
  const tileBackground =
    kind === "label" && config.colorByValue && Number.isFinite(levelValue)
      ? mixColor(config.gradientFrom || "#ffffff", config.gradientTo || "#d9f5df", levelPct / 100)
      : kind === "count" || kind === "online"
        ? config.background || undefined
        : undefined;

  const send = (next, commit) => {
    if (readOnly || !deviceId) return;
    setOptimistic(next);
    if (!commit) return;
    const isSwitch = kind === "switch";
    onCommand?.({
      deviceId,
      command: config.command || metric,
      type: isSwitch ? (next ? "on" : "off") : "value",
      value: next,
    });
  };

  const boundDevice = useMemo(
    () => (deviceId ? devices.find((d) => String(d.id) === String(deviceId)) : null),
    [devices, deviceId]
  );

  return (
    <div
      className={cn(
        "wb-card wb-placed group relative flex h-full flex-col overflow-hidden rounded-xl border border-slate-200/80 bg-white p-3 shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-all duration-150 hover:border-slate-300 hover:shadow-sm",
        editing && "wb-placed-edit ring-1 ring-transparent hover:ring-primary/40",
        widget.pinned && "wb-placed-pin ring-2 ring-emerald-500/80"
      )}
      style={tileBackground ? { background: tileBackground } : undefined}
    >
      <div className="wb-placed-head widget-drag-handle flex items-center justify-between gap-1.5 pb-1 select-none relative z-10">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {editing && !readOnly ? (
            <span
              className="text-slate-400 group-hover:text-primary transition-colors cursor-grab active:cursor-grabbing shrink-0"
              title="Drag to reposition widget"
            >
              <DotsSixVertical size={14} weight="bold" />
            </span>
          ) : null}
          {hideTitle ? null : (
            <span className="wb-card-title text-[11px] font-semibold text-slate-500 uppercase tracking-wider truncate" title={title}>
              {title}
            </span>
          )}
          {config.upgrade ? (
            <span className={cn("wb-upgrade shrink-0", config.upgrade === "enterprise" && "wb-upgrade-enterprise")}>
              Upgrade
            </span>
          ) : null}
        </div>

        {/* Live Device Integration Indicator */}
        {boundDevice && (boundDevice.name || boundDevice.label || boundDevice.device_uid) ? (
          <span
            className="flex shrink-0 items-center gap-1.5 text-[10px] font-mono text-slate-400"
            title={`Device: ${boundDevice.name || boundDevice.label || boundDevice.device_uid} (${boundDevice.status || "offline"})`}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                boundDevice.status === "online" ? "bg-emerald-500" : "bg-slate-300"
              )}
            />
            <span className="max-w-[80px] truncate">{boundDevice.name || boundDevice.label || boundDevice.device_uid}</span>
          </span>
        ) : editing && !readOnly && kind !== "table" && widget.type !== "device_table" && !deviceId ? (
          <button
            type="button"
            className="flex shrink-0 items-center gap-1 rounded-full bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-400 border border-dashed border-slate-300 hover:border-primary/60 hover:text-primary hover:bg-primary/5 transition-colors cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              onConfigure?.(widget);
            }}
            title="Click to bind a device"
          >
            + Bind
          </button>
        ) : null}
      </div>

      {editing && !readOnly ? (
        <div
          className="wb-placed-tools absolute right-2 top-2 z-20 flex items-center gap-0.5 rounded-lg border border-slate-200/90 bg-white/95 p-0.5 shadow-md backdrop-blur-md opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="h-6 w-6 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 flex items-center justify-center transition-colors"
            title="Rotate widget (horizontal / vertical)"
            aria-label="Rotate"
            onClick={() => onRotate?.(widget)}
          >
            <ArrowsClockwise size={13} weight="bold" />
          </button>
          <button
            type="button"
            className="h-6 w-6 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 flex items-center justify-center transition-colors"
            title="Duplicate widget"
            aria-label="Duplicate"
            onClick={() => onDuplicate?.(widget)}
          >
            <Copy size={13} weight="bold" />
          </button>
          <button
            type="button"
            className="h-6 w-6 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 flex items-center justify-center transition-colors"
            title="Widget settings"
            aria-label="Settings"
            onClick={() => onConfigure?.(widget)}
          >
            <GearSix size={13} weight="bold" />
          </button>
          <button
            type="button"
            className="h-6 w-6 rounded-md text-rose-500 hover:bg-rose-50 hover:text-rose-700 flex items-center justify-center transition-colors"
            title="Delete widget"
            aria-label="Delete"
            onClick={() => onDelete?.(widget)}
          >
            <Trash size={13} weight="bold" />
          </button>
        </div>
      ) : null}
      <div className="wb-placed-body widget-drag-handle flex-1 min-h-0 flex flex-col justify-center overflow-hidden relative z-10">
        {kind === "table" || config.variant === "table" || config.paletteId === "device_table" || widget.type === "device_table" ? (
          <DeviceTableWidget widget={widget} readOnly={readOnly} />
        ) : (
          <WidgetPalettePreview
            kind={kind}
            value={shown}
            on={switchedOn}
            points={points.length > 1 ? points : undefined}
            sliderMin={config.min}
            sliderMax={config.max}
            showFineControls={kind === "slider" && Boolean(config.showFineControls)}
            valuePosition={config.valuePosition || "left"}
            fineStep={config.step || 1}
            readOnly={readOnly || !deviceId}
            stateLabel={
              kind === "switch" && showLabels
                ? switchedOn
                  ? config.onLabel || "ON"
                  : config.offLabel || "OFF"
                : undefined
            }
            labelPosition={config.labelPosition || "right"}
            color={config.color}
            figure={tileFigure}
            tileAlign={config.align}
            showLevel={Boolean(config.showLevel)}
            levelColor={config.levelColor || "#2f6fed"}
            levelPosition={config.levelPosition || "horizontal"}
            levelPct={levelPct}
            orientation={config.orientation || (widget.layout?.h > widget.layout?.w ? "vertical" : "horizontal")}
            unit={config.unit}
            totalDevices={scopedDevices.length}
            onlineDevices={scopedDevices.filter((d) => d.status === "online").length}
            isPlaced={true}
            onToggle={
              kind === "switch" && deviceId
                ? (next) => send(next ? 1 : 0, true)
                : undefined
            }
            onSlide={
              kind === "slider" && deviceId
                ? (next, commit) => send(next, commit)
                : undefined
            }
          />
        )}
      </div>
    </div>
  );
}
