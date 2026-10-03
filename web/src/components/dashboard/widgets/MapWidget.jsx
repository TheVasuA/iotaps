import { MapPin, Broadcast, SquaresFour, GlobeHemisphereWest } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useAppSelector } from "@/store/hooks";
import { selectLatest } from "@/store/dashboardsSlice";
import { selectDevices } from "@/store/devicesSlice";
import { readMetric } from "@/lib/widgets";
import { UnboundNotice } from "./ChartWidget";

// Map widget (Req 7.3, 7.4). One `type: "map"`, three visual modes, selected by
// the palette entry that placed it (`config.paletteId`) so each toolbox tile
// keeps the identity it advertised:
//
//   geomap    — device position on a real chart surface (OpenStreetMap)
//   image_map — readings pinned to zones on a floor-plan image
//   status_map— connection health across the fleet, as a status board
//
// The toolbox previews in WidgetPalettePreview.jsx mirror these three shapes.

/** Floor-plan zones for image_map. Positions are percentages of the plan box. */
const ZONES = [
  { id: "A", label: "Zone A", metric: "humidity", unit: "%", x: 18, y: 42, tone: "emerald" },
  { id: "B", label: "Zone B", metric: "temp", unit: "°C", x: 54, y: 26, tone: "blue" },
  { id: "C", label: "Zone C", metric: "co2", unit: "", x: 82, y: 58, tone: "amber" },
];

const TONE_CHIP = {
  emerald:
    "border-emerald-200/80 text-emerald-700 dark:border-emerald-500/30 dark:text-emerald-400",
  blue: "border-blue-200/80 text-blue-700 dark:border-blue-500/30 dark:text-blue-400",
  amber: "border-amber-200/80 text-amber-700 dark:border-amber-500/30 dark:text-amber-400",
};

const STATUS_TONE = {
  online: "bg-emerald-500",
  degraded: "bg-amber-500",
  warn: "bg-amber-500",
  offline: "bg-slate-400",
};

function formatReading(value, unit) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  const text = Number.isFinite(n)
    ? Number.isInteger(n)
      ? String(n)
      : n.toFixed(1)
    : String(value);
  return unit ? `${text}${unit}` : text;
}

export default function MapWidget({ widget }) {
  const config = widget.config || {};
  // `paletteId` is written by the dashboard drop handler; fall back to `map`
  // for widgets created before the three previews diverged.
  const variant = config.paletteId === "image_map" || config.paletteId === "status_map"
    ? config.paletteId
    : "geomap";

  if (variant === "image_map") return <ImageMapWidget widget={widget} config={config} />;
  if (variant === "status_map") return <StatusMapWidget widget={widget} config={config} />;
  return <GeoMapWidget widget={widget} config={config} />;
}

/* ------------------------------------------------------------------ geomap */

function GeoMapWidget({ widget, config }) {
  const deviceId = config.deviceId;
  const latMetric = config.latMetric || "lat";
  const lonMetric = config.lonMetric || "lon";

  const latest = useAppSelector(selectLatest(deviceId));
  const lat = readMetric(latest?.data, latMetric);
  const lon = readMetric(latest?.data, lonMetric);

  if (!deviceId) return <UnboundNotice />;

  if (lat == null || lon == null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1 p-3 text-center text-xs text-muted-foreground">
        <MapPin size={22} />
        Waiting for location ({latMetric}/{lonMetric})
      </div>
    );
  }

  const delta = 0.01;
  const bbox = `${lon - delta},${lat - delta},${lon + delta},${lat + delta}`;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(
    bbox
  )}&layer=mapnik&marker=${lat},${lon}`;

  return (
    <div className="flex h-full flex-col">
      <iframe
        title={`map-${widget.id}`}
        src={src}
        className="h-full w-full flex-1 rounded-md border border-border"
        loading="lazy"
      />
      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin size={12} weight="fill" className="text-emerald-500" />
          <span className="truncate">{config.label || "Device position"}</span>
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {lat.toFixed(5)}, {lon.toFixed(5)}
        </span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- image_map */

function ImageMapWidget({ widget, config }) {
  const deviceId = config.deviceId;
  const latest = useAppSelector(selectLatest(deviceId));

  if (!deviceId) return <UnboundNotice />;

  return (
    <div className="flex h-full flex-col">
      {/* Floor plan. Inert by design: the plan is a schematic the hotspots sit
          on, so it is marked decorative and carries no pointer interactions. */}
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-muted/40">
        <svg
          viewBox="0 0 200 110"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden
          className="absolute inset-0 h-full w-full"
        >
          <rect
            x="12"
            y="12"
            width="176"
            height="86"
            rx="3"
            className="fill-background/70 stroke-border"
            strokeWidth="1.25"
          />
          <path
            d="M78 12 L78 98 M78 54 L142 54 M142 12 L142 98"
            fill="none"
            className="stroke-border"
            strokeWidth="1.25"
          />
          <path
            d="M78 28 L78 42 M78 68 L78 84 M142 24 L142 40"
            fill="none"
            className="stroke-background/80"
            strokeWidth="2.5"
          />
        </svg>

        {ZONES.map((zone) => (
          <div
            key={zone.id}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${zone.x}%`, top: `${zone.y}%` }}
          >
            <div
              className={cn(
                "flex flex-col items-center rounded-md border bg-background/95 px-2 py-1 shadow-xs",
                TONE_CHIP[zone.tone]
              )}
            >
              <span className="text-xs font-bold leading-none tabular-nums">
                {formatReading(readMetric(latest?.data, zone.metric), zone.unit)}
              </span>
              <span className="mt-0.5 text-[9px] font-medium uppercase tracking-wide opacity-75">
                {zone.label}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-1 px-1 pt-1 text-xs text-muted-foreground">
        <SquaresFour size={12} className="shrink-0" />
        <span className="truncate">Floor plan · {ZONES.length} zones</span>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- status_map */

function StatusMapWidget({ widget }) {
  const config = widget.config || {};
  // Same group scoping WidgetCard applies to its device counts. Status is
  // connection health, so this variant needs no per-device metric binding.
  const devices = useAppSelector(selectDevices);
  const scoped =
    config.groupId != null
      ? (devices || []).filter((d) => String(d.group_id) === String(config.groupId))
      : devices || [];
  const list = scoped.slice(0, 12);

  // "degraded" and "warn" are the same mid-tier to a viewer; collapse them.
  const counts = { online: 0, degraded: 0, offline: 0 };
  for (const device of list) {
    const status = device.status === "online" ? "online"
      : device.status === "offline" ? "offline"
      : "degraded";
    counts[status] += 1;
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 pb-1.5">
        <span className="flex items-center gap-1 rounded-full border border-border bg-muted/40 px-1.5 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          <span className="text-[10px] font-semibold tabular-nums">{counts.online}</span>
        </span>
        <span className="flex items-center gap-1 rounded-full border border-border bg-muted/40 px-1.5 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          <span className="text-[10px] font-semibold tabular-nums">{counts.degraded}</span>
        </span>
        <span className="flex items-center gap-1 rounded-full border border-border bg-muted/40 px-1.5 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
          <span className="text-[10px] font-semibold tabular-nums">{counts.offline}</span>
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
          <Broadcast size={12} className="shrink-0" />
          {list.length} device{list.length === 1 ? "" : "s"}
        </span>
      </div>

      {list.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 p-3 text-center text-xs text-muted-foreground">
          <GlobeHemisphereWest size={20} />
          No devices in this dashboard yet
        </div>
      ) : (
        <ul className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border">
          {list.map((device) => {
            const status = STATUS_TONE[device.status] ? device.status : "offline";
            return (
              <li
                key={device.id || device.device_uid}
                className="flex items-center gap-2 border-b border-border px-2 py-1.5 last:border-b-0"
              >
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", STATUS_TONE[status])} />
                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                  {device.name || device.label || device.device_uid}
                </span>
                <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {status}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
