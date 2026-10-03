import {
  Power,
  Broadcast,
  HardDrives,
  Cpu,
  Minus,
  Plus,
  Lightning,
  MapPin,
  Bell,
  Pulse,
  SquaresFour,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/** Value chip pinned onto a floor-plan zone in the image-map preview. */
function Hotspot({ value, label, tone }) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-200/80 text-emerald-700 dark:border-emerald-500/30 dark:text-emerald-400"
      : tone === "blue"
        ? "border-blue-200/80 text-blue-700 dark:border-blue-500/30 dark:text-blue-400"
        : "border-amber-200/80 text-amber-700 dark:border-amber-500/30 dark:text-amber-400";
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-md border bg-white/95 px-1.5 py-0.5 shadow-xs dark:bg-slate-900/85",
        toneClass
      )}
    >
      <span className="text-[10px] font-bold leading-none tabular-nums">{value}</span>
      <span className="mt-0.5 text-[8px] font-medium uppercase tracking-wide opacity-75">{label}</span>
    </div>
  );
}

function TileNumber({ text, align, showLevel, levelColor, levelPosition, levelPct, background }) {
  return (
    <div
      className={cn(
        "wb-tile flex flex-col justify-center",
        align === "center" ? "text-center items-center" : align === "right" ? "text-right items-end" : "text-left items-start"
      )}
      style={background ? { background } : undefined}
    >
      {showLevel && levelPosition === "vertical" ? (
        <span className="wb-level-v" style={{ background: levelColor }} />
      ) : null}
      <p className="wb-figure text-3xl lg:text-4xl font-black tracking-tight text-slate-900 tabular-nums">{text}</p>
      {showLevel && levelPosition !== "vertical" ? (
        <div className="mt-2 h-2 w-full rounded-full bg-slate-100 border border-slate-200/70 overflow-hidden shadow-inner">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${levelPct}%`, background: levelColor }}
          />
        </div>
      ) : null}
    </div>
  );
}

function showNum(value, fallback) {
  if (value == null || value === "") return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/** Modern, unique, state-of-the-art widget visuals for toolbox and dashboard canvas. */
export default function WidgetPalettePreview({
  kind,
  value,
  on = false,
  onToggle,
  onSlide,
  sliderMin = 0,
  sliderMax = 255,
  readOnly = false,
  points,
  stateLabel,
  labelPosition = "right",
  valuePosition = "left",
  showFineControls = false,
  fineStep = 1,
  color,
  figure,
  tileAlign,
  showLevel = false,
  levelColor = "#2f6fed",
  levelPosition = "horizontal",
  levelPct = 60,
  tileBackground,
  orientation = "horizontal",
  unit,
  totalDevices = 0,
  onlineDevices = 0,
  isPlaced = false,
}) {
  // 1. SWITCH WIDGET (MINIMAL UNIQUE PRECISION PILL)
  if (kind === "switch") {
    const isInteractive = Boolean(onToggle);

    return (
      <div className="flex flex-1 items-center justify-between px-0.5 select-none">
        <div className="flex flex-col justify-center">
          <span className="text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-200">
            {stateLabel || (on ? "Active" : "Inactive")}
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            {on ? "Relay closed" : "Relay open"}
          </span>
        </div>
        <button
          type="button"
          disabled={readOnly || !isInteractive}
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors duration-200 select-none",
            on
              ? "bg-emerald-600 shadow-xs"
              : "bg-slate-200 dark:bg-slate-700/80 hover:bg-slate-300 dark:hover:bg-slate-700",
            isInteractive && !readOnly ? "cursor-pointer" : "cursor-default"
          )}
          style={on && color ? { background: color } : undefined}
          aria-label={stateLabel || (on ? "Active" : "Inactive")}
          aria-pressed={on}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            if (isInteractive && !readOnly) onToggle(!on);
          }}
        >
          <span
            className={cn(
              "pointer-events-none block h-5 w-5 rounded-full bg-white shadow-xs transition-transform duration-200",
              on ? "translate-x-5" : "translate-x-0"
            )}
          />
        </button>
      </div>
    );
  }

  // 2. SLIDER WIDGET (MINIMAL INDUSTRIAL FADER)
  if (kind === "slider") {
    const isVertical = orientation === "vertical";
    const min = Number(sliderMin) || 0;
    const max = Number(sliderMax) || 255;
    const current = value == null || value === "" ? min : Number(value);
    const span = max - min || 1;
    const pct = Math.min(100, Math.max(0, ((current - min) / span) * 100));
    const step = Number(fineStep) || 1;
    const nudge = (direction) => {
      const next = Math.min(max, Math.max(min, (Number.isFinite(current) ? current : min) + direction * step));
      onSlide?.(next, true);
    };

    if (isVertical) {
      return (
        <div className="flex h-full w-full flex-col items-center justify-between py-1 select-none">
          <span className="text-base font-bold text-slate-900 tabular-nums">{showNum(value, String(min))}</span>
          <div className="relative flex-1 w-4 flex items-center justify-center my-1">
            <div className="absolute inset-y-0 w-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div
                className="absolute bottom-0 w-full rounded-full bg-slate-900 dark:bg-slate-100 transition-all duration-75"
                style={{ height: `${pct}%`, background: color || undefined }}
              />
            </div>
            <div
              className="pointer-events-none absolute w-3.5 h-3.5 rounded-full bg-white shadow-xs border border-slate-300 dark:border-slate-600 -translate-y-1/2"
              style={{ bottom: `calc(${pct}% - 7px)` }}
            />
            {onSlide ? (
              <input
                type="range"
                className="absolute inset-0 opacity-0 cursor-pointer"
                min={min}
                max={max}
                step={step}
                value={Number.isFinite(current) ? current : min}
                disabled={readOnly}
                aria-label="Slider"
                style={{ appearance: "slider-vertical", writingMode: "vertical-lr", direction: "rtl" }}
                onPointerDown={(event) => event.stopPropagation()}
                onChange={(event) => onSlide(Number(event.target.value), false)}
                onMouseUp={(event) => onSlide(Number(event.target.value), true)}
                onTouchEnd={(event) => onSlide(Number(event.currentTarget.value), true)}
              />
            ) : null}
          </div>
          <span className="text-[10px] font-mono text-slate-400">{Math.round(pct)}%</span>
        </div>
      );
    }

    // Horizontal Minimal Slider
    return (
      <div className="flex flex-1 flex-col justify-center px-0.5 select-none">
        <div className="flex items-baseline justify-between mb-1.5">
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
              {showNum(value, String(min))}
            </span>
            {unit ? (
              <span className="text-[11px] font-medium text-slate-400 uppercase">{unit}</span>
            ) : null}
          </div>
          <span className="text-[10px] font-mono text-slate-400">
            {Math.round(pct)}%
          </span>
        </div>

        <div className="flex items-center gap-2">
          {showFineControls ? (
            <button
              type="button"
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Decrease"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                nudge(-1);
              }}
            >
              <Minus size={10} weight="bold" />
            </button>
          ) : null}

          {/* Minimal Slider Track */}
          <div className="relative flex-1 flex items-center h-4">
            <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 relative overflow-hidden">
              <div
                className="h-full rounded-full bg-slate-900 dark:bg-slate-100 transition-all duration-75"
                style={{ width: `${pct}%`, background: color || undefined }}
              />
            </div>
            <div
              className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-xs border border-slate-300 dark:border-slate-600 transition-transform"
              style={{ left: `${pct}%` }}
            />
            {onSlide ? (
              <input
                type="range"
                className="absolute inset-0 opacity-0 cursor-pointer"
                min={min}
                max={max}
                step={step}
                value={Number.isFinite(current) ? current : min}
                disabled={readOnly}
                aria-label="Slider"
                onPointerDown={(event) => event.stopPropagation()}
                onChange={(event) => onSlide(Number(event.target.value), false)}
                onMouseUp={(event) => onSlide(Number(event.target.value), true)}
                onTouchEnd={(event) => onSlide(Number(event.currentTarget.value), true)}
              />
            ) : null}
          </div>

          {showFineControls ? (
            <button
              type="button"
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Increase"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                nudge(1);
              }}
            >
              <Plus size={10} weight="bold" />
            </button>
          ) : null}
        </div>

        <div className="flex items-center justify-between text-[9px] font-mono text-slate-300 dark:text-slate-600 px-0.5 pt-1 leading-none">
          <span>{min}</span>
          <span>{max}</span>
        </div>
      </div>
    );
  }

  // 3. LABEL WIDGET (MINIMAL TELEMETRY DISPLAY)
  if (kind === "label") {
    const text = figure != null ? figure : showNum(value, "—");
    const isLive = value != null;

    if (tileAlign === "center" || tileAlign === "right" || (showLevel && levelPosition !== "vertical") || tileBackground) {
      return (
        <TileNumber
          text={text}
          align={tileAlign}
          showLevel={showLevel}
          levelColor={levelColor}
          levelPosition={levelPosition}
          levelPct={levelPct}
          background={tileBackground}
        />
      );
    }

    return (
      <div className="flex flex-1 flex-col justify-center px-0.5 select-none">
        <div className="flex items-baseline gap-1.5">
          <span className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
            {text}
          </span>
          {unit ? (
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              {unit}
            </span>
          ) : null}
        </div>

        {showLevel ? (
          <div className="mt-2 h-1 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${levelPct}%`, background: levelColor || undefined }}
            />
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
            <span className={cn("h-1.5 w-1.5 rounded-full", isLive ? "bg-emerald-500" : "bg-slate-300")} />
            <span>{isLive ? "Live telemetry" : "Awaiting signal"}</span>
          </div>
        )}
      </div>
    );
  }

  // 4. DEVICE COUNT WIDGET (MINIMAL HARDWARE METRIC)
  if (kind === "count") {
    const text = figure != null ? figure : showNum(value, "0");
    return (
      <div className="flex flex-1 items-center justify-between px-0.5 select-none">
        <div className="flex flex-col justify-center">
          <span className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
            {text}
          </span>
          <span className="mt-1 text-[11px] font-medium text-slate-400">
            Total devices
          </span>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 text-slate-400">
          <HardDrives size={18} weight="regular" />
        </div>
      </div>
    );
  }

  // 5. DEVICES ONLINE NOW WIDGET (MINIMAL CONNECTIVITY STATUS)
  if (kind === "online") {
    const text = figure != null ? figure : showNum(value, "0");
    const onlineNum = Number(text) || 0;
    const totalNum = totalDevices || (onlineNum > 0 ? onlineNum : 1);
    const onlinePct = Math.min(100, Math.max(0, Math.round((onlineNum / totalNum) * 100)));

    return (
      <div className="flex flex-1 flex-col justify-center px-0.5 select-none">
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
              {text}
            </span>
            <span className="text-xs font-medium text-slate-400">
              / {totalDevices || 1} online
            </span>
          </div>
          <span className="flex h-2 w-2 relative">
            <span className={cn("animate-ping absolute inline-flex h-full w-full rounded-full opacity-75", onlineNum > 0 ? "bg-emerald-400" : "hidden")} />
            <span className={cn("relative inline-flex rounded-full h-2 w-2", onlineNum > 0 ? "bg-emerald-500" : "bg-slate-300")} />
          </span>
        </div>

        <div className="mt-2.5">
          <div className="h-1 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all duration-300"
              style={{ width: `${onlinePct}%` }}
            />
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>Availability</span>
            <span>{onlinePct}%</span>
          </div>
        </div>
      </div>
    );
  }

  // 6. TABLE WIDGET (TOOLBOX PREVIEW)
  if (kind === "table") {
    return (
      <div className="flex flex-col gap-1 w-full text-left py-0.5 select-none">
        <div className="flex items-center justify-between text-[10px] font-semibold text-slate-400 border-b border-slate-100 pb-1">
          <span>Device</span>
          <span>Status</span>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs py-0.5">
            <span className="font-medium text-slate-700 truncate text-[11px]">Sensor Node A</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-600">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Online
            </span>
          </div>
          <div className="flex items-center justify-between text-xs py-0.5">
            <span className="font-medium text-slate-700 truncate text-[11px]">Gateway Hub</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-600">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Online
            </span>
          </div>
        </div>
      </div>
    );
  }

  // 7. EVENT COUNT TILE
  if (kind === "event_num") {
    const count = showNum(value, "24");
    return (
      <div className="flex flex-1 items-center justify-between px-0.5 select-none">
        <div className="flex flex-col justify-center">
          <span className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 tabular-nums leading-none">
            {count}
          </span>
          <span className="mt-1 text-[11px] font-medium text-slate-400">
            Events logged (24h)
          </span>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 text-slate-400">
          <Lightning size={18} weight="regular" />
        </div>
      </div>
    );
  }

  // 8. GEOMAP TILE — one live position on a miniature geographic surface.
  // Reads as "a pin on a chart": graticule + coastline hint + a travelled
  // track terminating at the marker. Deliberately not a status chip.
  if (kind === "geomap") {
    return (
      <div className="relative flex flex-1 flex-col overflow-hidden rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 select-none">
        <svg
          viewBox="0 0 160 60"
          preserveAspectRatio="xMidYMid slice"
          aria-hidden
          className="absolute inset-0 h-full w-full"
        >
          <defs>
            <pattern id="wb-geo-grid" width="16" height="15" patternUnits="userSpaceOnUse">
              <path d="M16 0 L0 0 0 15" fill="none" stroke="currentColor" strokeWidth="0.5" />
            </pattern>
          </defs>
          {/* graticule */}
          <rect width="160" height="60" className="text-slate-200 dark:text-slate-700/70" fill="url(#wb-geo-grid)" />
          {/* coastline / landmass hint */}
          <path
            d="M0 42 Q22 30 40 36 T78 30 Q98 22 118 30 T160 24 L160 60 L0 60 Z"
            className="fill-slate-100 dark:fill-slate-800"
          />
          <path
            d="M0 42 Q22 30 40 36 T78 30 Q98 22 118 30 T160 24"
            fill="none"
            className="stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1"
          />
          {/* travelled track */}
          <path
            d="M18 48 L44 40 L70 43 L96 28 L118 22"
            fill="none"
            strokeWidth="1.25"
            strokeLinecap="round"
            strokeDasharray="3 2.5"
            className="stroke-emerald-500/70"
          />
          {/* start + current marker */}
          <circle cx="18" cy="48" r="2" className="fill-emerald-500/50" />
          <circle cx="118" cy="22" r="6.5" className="fill-emerald-500/25" />
          <circle cx="118" cy="22" r="2.75" className="fill-emerald-500 stroke-white" strokeWidth="1.25" />
        </svg>

        <div className="relative flex items-start justify-between gap-2 p-2">
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-200/70 bg-white/90 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700 dark:border-emerald-500/25 dark:bg-slate-900/80 dark:text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live
          </div>
          <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:bg-slate-900/70 dark:text-slate-400">
            1 node
          </span>
        </div>

        <div className="relative mt-auto flex items-end justify-between gap-2 px-2 pb-1.5">
          <div className="min-w-0">
            <p className="truncate text-[10px] font-semibold text-slate-700 dark:text-slate-200">
              Global Nodes Online
            </p>
            <p className="truncate font-mono text-[9px] tabular-nums text-slate-400">
              37.7749° N, 122.4194° W
            </p>
          </div>
          <MapPin size={13} weight="fill" className="shrink-0 text-emerald-500" />
        </div>
      </div>
    );
  }

  // 9. IMAGE / FLOOR MAP TILE — values pinned to zones on a plan drawing.
  // Reads as "annotated image": a blueprint with hotspots overlaid on it, not
  // a row of unrelated stats.
  if (kind === "image_map") {
    return (
      <div className="relative flex flex-1 flex-col overflow-hidden rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 select-none">
        {/* floor plan */}
        <svg
          viewBox="0 0 160 60"
          preserveAspectRatio="xMidYMid slice"
          aria-hidden
          className="absolute inset-0 h-full w-full"
        >
          <rect
            x="10"
            y="8"
            width="140"
            height="44"
            rx="2"
            className="fill-white/70 dark:fill-slate-900/50 stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1"
          />
          {/* room divisions */}
          <path
            d="M62 8 L62 52 M62 30 L112 30 M112 8 L112 52"
            fill="none"
            className="stroke-slate-300 dark:stroke-slate-600"
            strokeWidth="1"
          />
          {/* door gaps */}
          <path
            d="M62 16 L62 24 M62 38 L62 46 M112 14 L112 22"
            fill="none"
            className="stroke-slate-50 dark:stroke-slate-800/40"
            strokeWidth="1.5"
          />
        </svg>

        {/* zone hotspots — each anchored inside its room */}
        <div className="relative flex flex-1 items-stretch gap-1 p-2">
          <div className="flex w-[36%] flex-col items-start justify-center">
            <Hotspot value="45.5%" label="Zone A" tone="emerald" />
          </div>
          <div className="flex flex-1 flex-col items-center justify-start pt-0.5">
            <Hotspot value="20.2°C" label="Zone B" tone="blue" />
          </div>
          <div className="flex w-[28%] flex-col items-end justify-center">
            <Hotspot value="0.34" label="Zone C" tone="amber" />
          </div>
        </div>

        <div className="relative flex items-center gap-1 px-2 pb-1.5">
          <SquaresFour size={11} className="shrink-0 text-slate-400" />
          <span className="truncate text-[9px] font-medium text-slate-500 dark:text-slate-400">
            Floor plan · 3 zones
          </span>
        </div>
      </div>
    );
  }

  // 9b. STATUS MAP TILE — connection health across a fleet topology.
  // Reads as "nodes and links": satellites colour-coded by link state around
  // a hub, which is what a connection-status map is actually about.
  if (kind === "status_map") {
    return (
      <div className="relative flex flex-1 flex-col overflow-hidden rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40 select-none">
        <svg
          viewBox="0 0 160 60"
          preserveAspectRatio="xMidYMid slice"
          aria-hidden
          className="absolute inset-0 h-full w-full"
        >
          {/* links: hub at 80,32 */}
          <g strokeWidth="1.25" strokeDasharray="2.5 2.5">
            <line x1="80" y1="32" x2="30" y2="16" className="stroke-emerald-400/70" />
            <line x1="80" y1="32" x2="28" y2="46" className="stroke-emerald-400/70" />
            <line x1="80" y1="32" x2="128" y2="14" className="stroke-amber-400/70" />
            <line x1="80" y1="32" x2="132" y2="48" className="stroke-slate-300 dark:stroke-slate-600" />
            <line x1="80" y1="32" x2="80" y2="12" className="stroke-emerald-400/70" />
          </g>

          {/* satellites */}
          <g>
            <circle cx="30" cy="16" r="4.5" className="fill-emerald-500 stroke-white" strokeWidth="1.25" />
            <circle cx="28" cy="46" r="4.5" className="fill-emerald-500 stroke-white" strokeWidth="1.25" />
            <circle cx="80" cy="12" r="4.5" className="fill-emerald-500 stroke-white" strokeWidth="1.25" />
            <circle cx="128" cy="14" r="4.5" className="fill-amber-500 stroke-white" strokeWidth="1.25" />
            <circle cx="132" cy="48" r="4.5" className="fill-slate-400 stroke-white" strokeWidth="1.25" />
          </g>

          {/* hub */}
          <circle cx="80" cy="32" r="10" className="fill-emerald-500/20" />
          <circle cx="80" cy="32" r="6" className="fill-slate-900 stroke-white dark:fill-slate-100" strokeWidth="1.5" />
        </svg>

        <div className="relative flex items-start justify-between gap-2 p-2">
          <div className="flex items-center gap-1 rounded-full border border-slate-200/80 bg-white/90 px-1.5 py-0.5 dark:border-slate-700 dark:bg-slate-900/80">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span className="text-[9px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">3</span>
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            <span className="text-[9px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">1</span>
            <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
            <span className="text-[9px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">1</span>
          </div>
          <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:bg-slate-900/70 dark:text-slate-400">
            5 devices
          </span>
        </div>

        <div className="relative mt-auto flex items-end justify-between gap-2 px-2 pb-1.5">
          <div className="min-w-0">
            <p className="truncate text-[10px] font-semibold text-slate-700 dark:text-slate-200">
              Connection status
            </p>
            <p className="truncate text-[9px] text-slate-400">
              3 online · 1 degraded · 1 offline
            </p>
          </div>
              <Broadcast size={13} className="shrink-0 text-slate-400" />
        </div>
      </div>
    );
  }

  // 10. TIME-SERIES SPARKLINES
  if (kind === "line_dual") return <Spark colors={["#0f172a", "#10b981"]} points={points} />;
  if (kind === "line_multi") return <Spark colors={["#3b82f6", "#8b5cf6", "#10b981"]} points={points} />;
  if (kind === "line_green") return <Spark colors={["#10b981"]} points={points} />;
  if (kind === "line_lime") return <Spark colors={["#84cc16"]} points={points} />;

  // 11. HORIZONTAL EVENT BARS
  if (kind === "hbar") {
    return (
      <div className="flex flex-1 flex-col justify-center gap-1.5 px-0.5 select-none">
        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 pb-0.5">
            <span>Critical alerts</span>
            <span className="font-mono text-slate-400">{showNum(value, "44")}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div className="h-full rounded-full bg-slate-900 dark:bg-slate-200" style={{ width: "78%" }} />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 pb-0.5">
            <span>Warnings</span>
            <span className="font-mono text-slate-400">30</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div className="h-full rounded-full bg-slate-500 dark:bg-slate-400" style={{ width: "54%" }} />
          </div>
        </div>
      </div>
    );
  }

  // 12. STACKED EVENT BREAKDOWN
  if (kind === "stacked") {
    return (
      <div className="flex flex-1 flex-col justify-center gap-1.5 px-0.5 select-none">
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
          <span>Fleet telemetry split</span>
          <span className="font-semibold text-slate-700 dark:text-slate-300">142 total</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden flex gap-0.5">
          <div className="h-full bg-slate-900 dark:bg-slate-100 rounded-l-full" style={{ width: "45%" }} />
          <div className="h-full bg-slate-500" style={{ width: "35%" }} />
          <div className="h-full bg-slate-300 dark:bg-slate-600 rounded-r-full" style={{ width: "20%" }} />
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-400 pt-0.5">
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-slate-900 dark:bg-slate-100" />Sensors</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-slate-500" />Gateways</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-slate-300" />Relays</span>
        </div>
      </div>
    );
  }

  // 13. LATEST EVENTS FEED
  if (kind === "events") {
    return (
      <div className="flex flex-1 flex-col justify-center gap-1.5 px-0.5 select-none">
        <div className="flex items-center justify-between py-1 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            <span className="text-xs font-medium text-slate-700 dark:text-slate-200 truncate max-w-[120px]">
              Firmware check
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-400">Just now</span>
        </div>
        <div className="flex items-center justify-between py-1">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span className="text-xs font-medium text-slate-700 dark:text-slate-200 truncate max-w-[120px]">
              Telemetry ping
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-400">2m ago</span>
        </div>
      </div>
    );
  }

  return <p className="wb-figure text-3xl font-bold text-slate-900 tabular-nums">—</p>;
}

function Spark({ colors, points }) {
  const paths = [
    "M0 24 L16 16 L32 20 L48 8 L64 16 L80 10 L96 14 L112 4",
    "M0 30 L16 26 L32 16 L48 18 L64 8 L80 12 L96 6 L112 10",
  ];
  const live = Array.isArray(points) && points.length > 1 ? sparkPath(points) : null;
  return (
    <div className="flex flex-1 items-center justify-center w-full px-1">
      <svg viewBox="0 0 112 36" className="w-full h-9 stroke-slate-800 dark:stroke-slate-200" preserveAspectRatio="none" aria-hidden>
        {colors.map((color, i) => (
          <path
            key={color || i}
            d={i === 0 && live ? live : paths[i % paths.length]}
            fill="none"
            stroke={color || "currentColor"}
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-all"
          />
        ))}
      </svg>
    </div>
  );
}

function sparkPath(points) {
  const w = 112;
  const h = 36;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = w / (points.length - 1);
  return points
    .map((value, index) => {
      const x = index * step;
      const y = h - ((value - min) / range) * (h - 8) - 4;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}
