import { useEffect, useMemo, useState } from "react";
import {
  CaretRight,
  CaretDown,
  Circle,
  Broadcast,
  WifiHigh,
  MagnifyingGlass,
  BracketsCurly,
} from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { fetchDevices, selectDevices } from "@/store/devicesSlice";
import useDashboardTelemetry from "@/lib/useDashboardTelemetry";
import { cn } from "@/lib/utils";

// IoT Explorer — live view of *connected* devices and the JSON structure of
// their latest telemetry payload. Surfaces the raw MQTT topic + decoded JSON.
// Only devices currently online are shown (Req: connected devices only).

function isContainer(value) {
  return value !== null && typeof value === "object";
}

function formatPrimitive(value) {
  if (typeof value === "string") return `"${value}"`;
  return String(value);
}

function JsonNode({ name, value, depth = 0, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  const container = isContainer(value);

  if (!container) {
    return (
      <div
        className="flex items-center gap-1.5 py-0.5"
        style={{ paddingLeft: depth * 16 + 18 }}
      >
        <Circle size={7} weight="fill" className="shrink-0 text-emerald-500" />
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
    <div>
      <div
        className="flex cursor-pointer select-none items-center gap-1.5 rounded-md py-0.5 hover:bg-accent/50"
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

function DeviceNode({ device, telemetry }) {
  const [open, setOpen] = useState(true);
  const topic = `iotaps/${device.org_id}/${device.id}/telemetry`;
  const data = telemetry?.data ?? null;
  const hasData = isContainer(data) || data != null;

  return (
    <div className="border-b border-border/60 last:border-b-0">
      <button
        type="button"
        className="flex w-full cursor-pointer select-none items-center gap-2.5 px-3 py-3 text-left transition-colors hover:bg-accent/40"
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <CaretDown size={15} className="shrink-0 text-muted-foreground" />
        ) : (
          <CaretRight size={15} className="shrink-0 text-muted-foreground" />
        )}
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
          )}
        >
          <Broadcast size={15} weight="duotone" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-foreground">
            {device.label || device.device_uid || device.id}
          </span>
          <span className="block truncate font-mono text-[11px] text-muted-foreground">
            {topic}
          </span>
        </span>
        <Badge variant="success" className="shrink-0 text-[10px]">
          <WifiHigh size={11} />
          online
        </Badge>
        {telemetry?.ts ? (
          <span className="shrink-0 text-[10px] text-muted-foreground">
            {new Date(telemetry.ts).toLocaleTimeString()}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="border-t border-border/40 bg-muted/15 px-3 py-2.5">
          {hasData ? (
            <JsonNode name="payload" value={data} defaultOpen />
          ) : (
            <p className="pl-[18px] text-xs text-muted-foreground">
              Waiting for telemetry…
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function MqttExplorerPage() {
  const dispatch = useAppDispatch();
  const devices = useAppSelector(selectDevices);
  const latest = useAppSelector((s) => s.dashboards.latest);
  const [filter, setFilter] = useState("");

  // Load the fleet when landing here directly (store may be empty on a cold visit).
  useEffect(() => {
    if (devices.length === 0) dispatch(fetchDevices());
  }, [dispatch, devices.length]);

  const onlineDevices = useMemo(
    () => devices.filter((d) => d.status === "online"),
    [devices]
  );

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
    <div className="devices-screen">
      <header className="devices-hero">
        <div className="devices-hero-grid" aria-hidden />
        <div className="devices-hero-inner">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              Live stream
            </p>
            <h1 className="mt-1 flex items-center gap-2.5 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              <Broadcast size={28} className="text-primary" />
              IoT Explorer
            </h1>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Inspect live JSON telemetry from every connected device — topics, payloads, and timestamps.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="success" className="text-xs">
              <WifiHigh size={12} />
              {onlineDevices.length} connected
            </Badge>
            <div className="relative w-52">
              <MagnifyingGlass
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                placeholder="Filter devices..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="h-10 pl-9 text-sm"
              />
            </div>
          </div>
        </div>
      </header>

      <div className="devices-panel mt-4 overflow-hidden">
        {filtered.length === 0 ? (
          <div className="devices-empty m-4 border-0">
            <span className="devices-empty-icon">
              <BracketsCurly size={28} weight="duotone" />
            </span>
            <h2 className="mt-4 text-base font-semibold text-foreground">
              {onlineDevices.length === 0
                ? "No connected devices"
                : "No devices match your filter"}
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {onlineDevices.length === 0
                ? "Bring a device online to inspect its live JSON telemetry here."
                : "Try a different device name, UID, or ID."}
            </p>
          </div>
        ) : (
          <div className="font-mono text-sm">
            {filtered.map((device) => (
              <DeviceNode
                key={device.id}
                device={device}
                telemetry={latest[device.id] || null}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
