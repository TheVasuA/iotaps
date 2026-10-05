import { useEffect, useMemo, useState, memo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  Stack,
  MagnifyingGlass,
  ArrowClockwise,
  CircleNotch,
  Copy,
  Eye,
  EyeSlash,
  Cpu,
  WifiHigh,
  WifiSlash,
  Wrench,
  Trash,
  CaretRight,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDevices,
  fetchDeviceGroups,
  setFilters,
  updateDeviceStatus,
  saveDevice,
  removeDevice,
  selectDevices,
  selectDeviceGroups,
  selectDeviceFilters,
  selectDevicesStatus,
  selectDevicesError,
} from "@/store/devicesSlice";
import realtimeClient from "@/lib/realtime";
import ProvisioningWizard from "@/components/devices/ProvisioningWizard";
import GroupManager from "@/components/devices/GroupManager";

// Device list (Req 5.3-5.5): fleet overview with status, group, and label
// columns, search, status/group filters, provisioning wizard, and group manager.
const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
];

function CredentialCell({ value, secret }) {
  const [revealed, setRevealed] = useState(false);
  const hasValue = value && value !== "—";
  const display = secret && !revealed ? "••••••••" : (value || "—");
  const trimmed = display.length > 14 ? display.slice(0, 14) + "…" : display;

  const handleCopy = (e) => {
    e.stopPropagation();
    if (!hasValue) return;
    navigator.clipboard.writeText(value).then(() => {
      toast.success("Copied to clipboard");
    });
  };

  const handleToggle = (e) => {
    e.stopPropagation();
    setRevealed((r) => !r);
  };

  return (
    <div className="flex items-center gap-1">
      <code
        className="max-w-[120px] truncate rounded-md bg-muted/70 px-2 py-1 font-mono text-xs text-foreground"
        title={revealed ? value : undefined}
      >
        {trimmed}
      </code>
      {secret && hasValue && (
        <button
          type="button"
          onClick={handleToggle}
          className="devices-icon-btn h-7 w-7"
          title={revealed ? "Hide" : "Show"}
        >
          {revealed ? <EyeSlash size={13} /> : <Eye size={13} />}
        </button>
      )}
      {hasValue && (
        <button
          type="button"
          onClick={handleCopy}
          className="devices-icon-btn h-7 w-7"
          title="Copy"
        >
          <Copy size={13} />
        </button>
      )}
    </div>
  );
}

function StatusPill({ status }) {
  const online = status === "online";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
        online
          ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
          : "bg-muted text-muted-foreground"
      )}
    >
      <span
        className={cn(
          "devices-status-dot",
          online ? "devices-status-dot-online" : "devices-status-dot-offline"
        )}
      />
      {online ? "Online" : "Offline"}
    </span>
  );
}

function StatTile({ icon: Icon, label, value, tone }) {
  const tones = {
    brand: "bg-primary/10 text-primary",
    online: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
    offline: "bg-muted text-muted-foreground",
    warn: "bg-amber-500/12 text-amber-600 dark:text-amber-400",
  };
  return (
    <div className="devices-stat">
      <span className={cn("devices-stat-icon", tones[tone] || tones.brand)}>
        <Icon size={20} weight="duotone" />
      </span>
      <div>
        <p className="devices-stat-value">{value}</p>
        <p className="devices-stat-label">{label}</p>
      </div>
    </div>
  );
}

const DeviceRow = memo(function DeviceRow({ device: d, groupName, selected, onToggleSelect }) {
  const navigate = useNavigate();
  return (
    <tr
      className={cn(
        "group cursor-pointer transition-colors hover:bg-accent/40",
        selected && "bg-primary/[0.06]"
      )}
      onClick={() => navigate(`/devices/${d.id}`)}
    >
      <td className="w-10 px-3 py-3" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          aria-label={`Select ${d.label || d.device_uid}`}
          onChange={() => onToggleSelect(d.id)}
          className="h-4 w-4 rounded border-input"
        />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
              d.status === "online"
                ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
                : "bg-muted text-muted-foreground"
            )}
          >
            <Cpu size={18} weight="duotone" />
          </span>
          <div className="min-w-0">
            <div className="truncate font-medium text-foreground">
              {d.label || d.device_uid || "(unnamed)"}
            </div>
            {d.label && d.device_uid ? (
              <div className="truncate font-mono text-xs text-muted-foreground">
                {d.device_uid}
              </div>
            ) : null}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <StatusPill status={d.status} />
      </td>
      <td className="px-4 py-3">
        {groupName ? (
          <span className="devices-chip">{groupName}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {d.maintenance_mode ? (
          <Badge variant="warning">
            <Wrench size={11} /> Maintenance
          </Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <CredentialCell value={d.device_token} secret />
      </td>
      <td className="w-10 px-2 py-3 text-right">
        <CaretRight
          size={16}
          className="ml-auto text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        />
      </td>
    </tr>
  );
});

export default function DeviceListPage() {
  const dispatch = useAppDispatch();
  const devices = useAppSelector(selectDevices);
  const groups = useAppSelector(selectDeviceGroups);
  const filters = useAppSelector(selectDeviceFilters);
  const status = useAppSelector(selectDevicesStatus);
  const error = useAppSelector(selectDevicesError);

  const [search, setSearch] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [selected, setSelected] = useState(() => new Set());

  useEffect(() => {
    dispatch(
      fetchDevices({ groupId: filters.groupId, status: filters.status })
    );
  }, [dispatch, filters.groupId, filters.status]);

  useEffect(() => {
    dispatch(fetchDeviceGroups());
  }, [dispatch]);

  const deviceIds = useMemo(() => devices.map((d) => d.id).join(","), [devices]);

  useEffect(() => {
    if (!deviceIds) return;
    const ids = deviceIds.split(",");
    const unsubs = ids.map((id) =>
      realtimeClient.subscribe(`device:${id}`, (msg) => {
        if (msg.type === "status" && msg.device_id === id) {
          dispatch(updateDeviceStatus({ device_id: msg.device_id, status: msg.status }));
        }
      })
    );
    return () => unsubs.forEach((fn) => fn());
  }, [dispatch, deviceIds]);

  const groupName = (id) => groups.find((g) => g.id === id)?.name;

  const stats = useMemo(() => {
    const online = devices.filter((d) => d.status === "online").length;
    const maintenance = devices.filter((d) => d.maintenance_mode).length;
    return {
      total: devices.length,
      online,
      offline: Math.max(0, devices.length - online),
      maintenance,
    };
  }, [devices]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter((d) => {
      const label = (d.label || "").toLowerCase();
      const uid = (d.device_uid || "").toLowerCase();
      return label.includes(q) || uid.includes(q);
    });
  }, [devices, search]);

  const allVisibleSelected =
    visible.length > 0 && visible.every((d) => selected.has(d.id));

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(visible.map((d) => d.id)));
  };

  const bulkMaintenance = async (on) => {
    const ids = [...selected];
    await Promise.all(
      ids.map((id) => dispatch(saveDevice({ id, changes: { maintenanceMode: on } })).unwrap())
    );
    toast.success(`${ids.length} device(s) → maintenance ${on ? "ON" : "OFF"}`);
    setSelected(new Set());
  };

  const bulkDelete = async () => {
    if (!window.confirm(`Delete ${selected.size} device(s)?`)) return;
    const ids = [...selected];
    for (const id of ids) {
      await dispatch(removeDevice(id)).unwrap();
    }
    toast.success(`Deleted ${ids.length} device(s)`);
    setSelected(new Set());
  };

  const refresh = () =>
    dispatch(fetchDevices({ groupId: filters.groupId, status: filters.status }));

  return (
    <div className="devices-screen">
      <header className="devices-hero">
        <div className="devices-hero-grid" aria-hidden />
        <div className="devices-hero-inner">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              Fleet
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              Devices
            </h1>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Provision hardware, monitor connectivity, and manage credentials across your fleet.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => setGroupsOpen(true)}>
              <Stack size={16} />
              Groups
            </Button>
            <Button onClick={() => setWizardOpen(true)}>
              <Plus size={16} />
              Provision device
            </Button>
          </div>
        </div>
      </header>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={Cpu} label="Total devices" value={stats.total} tone="brand" />
        <StatTile icon={WifiHigh} label="Online" value={stats.online} tone="online" />
        <StatTile icon={WifiSlash} label="Offline" value={stats.offline} tone="offline" />
        <StatTile icon={Wrench} label="Maintenance" value={stats.maintenance} tone="warn" />
      </div>

      <div className="devices-toolbar mt-4">
        <div className="relative min-w-[12rem] flex-1">
          <MagnifyingGlass
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            className="pl-9"
            placeholder="Search by label or UID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label="Filter by status"
          value={filters.status || ""}
          onChange={(e) =>
            dispatch(setFilters({ status: e.target.value || null }))
          }
          className="devices-select"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by group"
          value={filters.groupId || ""}
          onChange={(e) =>
            dispatch(setFilters({ groupId: e.target.value || null }))
          }
          className="devices-select"
        >
          <option value="">All groups</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Refresh"
          onClick={refresh}
        >
          <ArrowClockwise size={16} />
        </Button>
      </div>

      {selected.size > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary/30 bg-primary/[0.07] px-3 py-2.5 text-sm">
          <span className="font-medium text-primary">{selected.size} selected</span>
          <Button size="sm" variant="outline" onClick={() => bulkMaintenance(true)}>
            Maintenance on
          </Button>
          <Button size="sm" variant="outline" onClick={() => bulkMaintenance(false)}>
            Maintenance off
          </Button>
          <Button size="sm" variant="destructive" onClick={bulkDelete}>
            <Trash size={14} /> Delete selected
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      ) : null}

      <div className="tb-entity-table mt-4">
        <table>
          <thead>
            <tr>
              <th className="w-10 px-3">
                <input
                  type="checkbox"
                  aria-label="Select all visible devices"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-input"
                />
              </th>
              <th className="px-4 py-3 font-medium">Device</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Group</th>
              <th className="px-4 py-3 font-medium">Maintenance</th>
              <th className="px-4 py-3 font-medium">Device Token</th>
              <th className="w-10 px-2 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {status === "loading" ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">
                  <CircleNotch size={22} className="mx-auto animate-spin" />
                  <p className="mt-2 text-sm">Loading fleet…</p>
                </td>
              </tr>
            ) : status === "failed" ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-destructive">
                  {error || "Failed to load devices"}
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-0 py-0">
                  <div className="devices-empty m-4 border-0">
                    <span className="devices-empty-icon">
                      <Cpu size={28} weight="duotone" />
                    </span>
                    <h2 className="mt-4 text-base font-semibold text-foreground">
                      {devices.length === 0
                        ? "No devices yet"
                        : "No devices match your filters"}
                    </h2>
                    <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                      {devices.length === 0
                        ? "Provision your first device to start receiving telemetry and sending commands."
                        : "Try adjusting search or filters to find the device you need."}
                    </p>
                    {devices.length === 0 ? (
                      <Button className="mt-5" onClick={() => setWizardOpen(true)}>
                        <Plus size={16} /> Provision device
                      </Button>
                    ) : (
                      <Button
                        className="mt-5"
                        variant="outline"
                        onClick={() => {
                          setSearch("");
                          dispatch(setFilters({ status: null, groupId: null }));
                        }}
                      >
                        Clear filters
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((d) => (
                <DeviceRow
                  key={d.id}
                  device={d}
                  groupName={groupName(d.group_id)}
                  selected={selected.has(d.id)}
                  onToggleSelect={toggleSelect}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {visible.length > 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Showing {visible.length} of {devices.length} device{devices.length === 1 ? "" : "s"}
        </p>
      ) : null}

      <ProvisioningWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
      />
      <GroupManager open={groupsOpen} onClose={() => setGroupsOpen(false)} />
    </div>
  );
}
