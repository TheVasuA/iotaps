import { useState, useMemo } from "react";
import {
  CaretRight,
  CaretDown,
  Circle,
  Broadcast,
  WifiHigh,
} from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/devicesSlice";
import useDashboardTelemetry from "@/lib/useDashboardTelemetry";

// IoT Explorer — live view of *connected* devices and the JSON structure of
// their latest telemetry payload. Unlike the dashboard, this surfaces the raw
// MQTT topic + the actual decoded JSON so users can inspect what a device is
// publishing. Only devices currently online are shown (Req: connected devices
// only); offline devices and synthetic broker ($SYS) topics are excluded.

function isContainer(value) {
  return value !== null && typeof value === "object";
}

/** Format a primitive telemetry value for display. */
function formatPrimitive(value) {
  if (typeof value === "string") return `"${value}"`;
  return String(value);
}

/** Recursive renderer for a decoded JSON payload (objects, arrays, primitives). */
function JsonNode({ name, value, depth = 0, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  const container = isContainer(value);

  if (!container) {
    return (
      <div
        className="flex items-center gap-1.5 py-0.5"
        style={{ paddingLeft: depth * 16 + 18 }}
      >
        <Circle
          size={7}
          weight="fill"
          className="shrink-0 text-emerald-500"
        />
        <span className="text-sm text-foreground">{name}</span>
        <code className="text-xs text-primary">: {formatPrimitive(value)}</code>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value);
  const typeLabel = Array.isArray(value)
    ? `[${entries.length}]`
    : `{${entries.length}}`;

  return (
    <div style={{ paddingLeft: depth > 0 ? 0 : 0 }}>
      <div
        className="flex cursor-pointer select-none items-center gap-1.5 rounded py-0.5 hover:bg-accent/50"
        style={{ paddingLeft: depth * 16 }}
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <CaretDown size={14} className="shrink-0 text-muted-foreground" />
        ) : (
          <CaretRight size={14} className="shrink-0 text-muted-foreground" />
        )}
        <span className="text-sm font-medium text-foreground">{name}</span>
        <span className="ml-1 text-[10px] text-muted-foreground">{typeLabel}</span>
      </div>
      {open &&
        entries.map(([k, v]) => (
          <JsonNode
            key={k}
            name={k}
            value={v}
            depth={depth + 1}
            defaultOpen={depth < 2}
          />
        ))}
    </div>
  );
}

/** A single connected device: its MQTT topic + latest telemetry JSON. */
function DeviceNode({ device, telemetry }) {
  const [open, setOpen] = useState(true);
  const topic = `iotaps/${device.org_id}/${device.id}/telemetry`;
  const data = telemetry?.data ?? null;
  const hasData = isContainer(data) || data != null;

  return (
    <div className="border-b border-border last:border-b-0">
      <div
        className="flex cursor-pointer select-none items-center gap-2 px-2 py-2 hover:bg-accent/40"
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <CaretDown size={15} className="shrink-0 text-muted-foreground" />
        ) : (
          <CaretRight size={15} className="shrink-0 text-muted-foreground" />
        )}
        <span className="text-sm font-semibold text-foreground">
          {device.label || device.device_uid || device.id}
        </span>
        <Badge variant="success" className="text-[10px]">
          <WifiHigh size={11} className="mr-0.5" />
          online
        </Badge>
        {telemetry?.ts && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {new Date(telemetry.ts).toLocaleTimeString()}
          </span>
        )}
      </div>
      {open && (
        <div className="px-2 pb-3">
          <div className="mb-1.5 truncate pl-[18px] text-[11px] text-muted-foreground">
            {topic}
          </div>
          {hasData ? (
            <JsonNode name="payload" value={data} defaultOpen />
          ) : (
            <p className="pl-[18px] text-xs text-muted-foreground">
              Waiting for telemetry…
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function MqttExplorerPage() {
  const devices = useAppSelector(selectDevices);
  const latest = useAppSelector((s) => s.dashboards.latest);
  const [filter, setFilter] = useState("");

  // Connected devices only (Req: show only connected devices).
  const onlineDevices = useMemo(
    () => devices.filter((d) => d.status === "online"),
    [devices]
  );

  // Subscribe to live telemetry for the connected devices so the JSON structure
  // reflects what each device is actually publishing.
  const onlineIds = useMemo(() => onlineDevices.map((d) => d.id), [onlineDevices]);
  useDashboardTelemetry(onlineIds);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return onlineDevices;
    return onlineDevices.filter((d) =>
      `${d.label || ""} ${d.device_uid || ""} ${d.id}`.toLowerCase().includes(q)
    );
  }, [onlineDevices, filter]);

  return (
    <section className="mx-auto max-w-5xl space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Broadcast size={22} className="text-primary" />
          <h1 className="text-xl font-bold">IoT Explorer</h1>
          <Badge variant="muted" className="text-[10px]">
            {onlineDevices.length} connected device
            {onlineDevices.length === 1 ? "" : "s"}
          </Badge>
        </div>
        <Input
          placeholder="Filter devices..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 w-48 text-sm"
        />
      </header>

      <div className="min-h-[60vh] overflow-auto rounded-xl border border-border bg-card font-mono text-sm">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Broadcast size={32} className="mb-2" />
            <p>No connected devices</p>
            <p className="text-xs">
              Bring a device online to inspect its live JSON telemetry here
            </p>
          </div>
        ) : (
          filtered.map((device) => (
            <DeviceNode
              key={device.id}
              device={device}
              telemetry={latest[device.id] || null}
            />
          ))
        )}
      </div>
    </section>
  );
}
