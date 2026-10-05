import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  FloppyDisk,
  Trash,
  UserPlus,
  CircleNotch,
  Copy,
  Eye,
  EyeSlash,
  CreditCard,
  Plugs,
  PlugsConnected,
  Broadcast,
  DownloadSimple,
  Cpu,
  Wrench,
  FolderOpen,
  Folder,
  FileText,
  Globe,
  CaretRight,
  CaretDown,
  Lightning,
  SlidersHorizontal,
  ClockCounterClockwise,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDevices,
  fetchDeviceGroups,
  saveDevice,
  removeDevice,
  upsertDevice,
  selectDeviceById,
  selectDeviceGroups,
  selectDevices,
} from "@/store/devicesSlice";
import { selectLatest } from "@/store/dashboardsSlice";
import { getDevice } from "@/lib/devicesApi";
import { exportTelemetryCsv } from "@/lib/telemetryApi";
import { extractApiError } from "@/lib/authApi";
import QrDisplay from "@/components/devices/QrDisplay";
import AssignUserDialog from "@/components/devices/AssignUserDialog";
import ToggleControl from "@/components/devices/ToggleControl";
import SliderControl from "@/components/devices/SliderControl";
import EntityTabs from "@/components/ui/EntityTabs";
import useDashboardTelemetry from "@/lib/useDashboardTelemetry";
import { useDeviceEventLog } from "@/lib/useDeviceEventLog";
import { issueCommand } from "@/lib/commandsApi";

const DEVICE_TABS = [
  { id: "overview", label: "Overview" },
  { id: "telemetry", label: "Telemetry" },
  { id: "attributes", label: "Attributes" },
  { id: "events", label: "Events" },
  { id: "commands", label: "Commands & RPC" },
];

const TOPIC_META = {
  telemetry: {
    dir: "↑ PUBLISH",
    dirClass: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
    blurb: "Device sends sensor data here on its telemetry interval.",
  },
  command: {
    dir: "↓ SUBSCRIBE",
    dirClass: "bg-blue-500/12 text-blue-600 dark:text-blue-400",
    blurb: "Device listens here for remote commands.",
  },
  ack: {
    dir: "↑ PUBLISH",
    dirClass: "bg-amber-500/12 text-amber-600 dark:text-amber-400",
    blurb: "Device confirms command execution.",
  },
  status: {
    dir: "LWT",
    dirClass: "bg-primary/12 text-primary",
    blurb: "Last Will & Testament for automatic offline detection.",
  },
};

function DeviceExplorer({ device, telemetryData }) {
  const [expanded, setExpanded] = useState({
    telemetry: true,
    command: false,
    ack: false,
    status: true,
  });
  const token = device.device_token || device.device_uid || device.id;
  const baseTopic = `iotaps/${token}`;

  const toggle = (key) => setExpanded((e) => ({ ...e, [key]: !e[key] }));

  const topics = [
    {
      key: "telemetry",
      name: "/telemetry",
      children: (
        <>
          <p className="pb-1 text-[11px] text-muted-foreground">
            {TOPIC_META.telemetry.blurb}
          </p>
          {Object.keys(telemetryData).length > 0 ? (
            Object.entries(telemetryData).map(([k, v]) => (
              <div key={k} className="devices-mqtt-leaf">
                <FileText size={13} className="shrink-0 text-muted-foreground" />
                <span className="text-muted-foreground">{k}</span>
                <span className="font-semibold text-primary">
                  {JSON.stringify(v)}
                </span>
              </div>
            ))
          ) : (
            <p className="devices-mqtt-leaf text-muted-foreground italic">
              Waiting for data…
            </p>
          )}
        </>
      ),
    },
    {
      key: "command",
      name: "/command",
      children: (
        <>
          <p className="pb-1 text-[11px] text-muted-foreground">
            {TOPIC_META.command.blurb}
          </p>
          <div className="devices-mqtt-leaf">
            <FileText size={13} className="shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">Format:</span>
            <code className="text-primary">
              {"{"}"type","target","value","command_id"{"}"}
            </code>
          </div>
        </>
      ),
    },
    {
      key: "ack",
      name: "/ack",
      children: (
        <>
          <p className="pb-1 text-[11px] text-muted-foreground">
            {TOPIC_META.ack.blurb}
          </p>
          <div className="devices-mqtt-leaf">
            <FileText size={13} className="shrink-0 text-muted-foreground" />
            <span className="text-muted-foreground">Format:</span>
            <code className="text-primary">
              {"{"}"command_id","status":"executed"{"}"}
            </code>
          </div>
        </>
      ),
    },
    {
      key: "status",
      name: "/status",
      children: (
        <>
          <p className="pb-1 text-[11px] text-muted-foreground">
            {TOPIC_META.status.blurb}
          </p>
          <div className="devices-mqtt-leaf">
            <span
              className={cn(
                "devices-status-dot",
                device.status === "online"
                  ? "devices-status-dot-online"
                  : "devices-status-dot-offline"
              )}
            />
            <span className="font-semibold text-foreground">{device.status}</span>
          </div>
        </>
      ),
    },
  ];

  return (
    <section className="devices-panel">
      <header className="devices-panel-head">
        <div className="devices-panel-title">
          <Broadcast size={16} className="text-primary" />
          MQTT Explorer
          <Badge variant="muted" className="text-[10px]">
            4 topics
          </Badge>
        </div>
      </header>
      <div className="overflow-hidden rounded-b-xl font-mono text-xs">
        <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-3 py-2.5">
          <Globe size={15} className="text-primary" />
          <span className="font-semibold text-foreground">{baseTopic}</span>
        </div>

        {topics.map((t) => {
          const meta = TOPIC_META[t.key];
          const open = expanded[t.key];
          return (
            <div key={t.key} className="border-b border-border/40 last:border-b-0">
              <button
                type="button"
                className="devices-mqtt-row w-full text-left"
                onClick={() => toggle(t.key)}
              >
                {open ? (
                  <CaretDown size={13} className="shrink-0 text-muted-foreground" />
                ) : (
                  <CaretRight size={13} className="shrink-0 text-muted-foreground" />
                )}
                {open ? (
                  <FolderOpen size={15} className="shrink-0 text-primary" />
                ) : (
                  <Folder size={15} className="shrink-0 text-primary/80" />
                )}
                <span className="font-medium text-foreground">{t.name}</span>
                <span
                  className={cn(
                    "ml-auto rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-wide",
                    meta.dirClass
                  )}
                >
                  {meta.dir}
                </span>
              </button>
              {open ? (
                <div className="bg-muted/15 px-3 pb-2.5 pt-1">{t.children}</div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CredentialField({ label, value, secret }) {
  const [revealed, setRevealed] = useState(false);
  const display = secret && !revealed ? "••••••••••••" : (value || "—");

  const copy = () => {
    if (!value) return;
    navigator.clipboard.writeText(value);
    toast.success(`${label} copied`);
  };

  return (
    <div className="space-y-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="flex items-center gap-1.5">
        <code className="devices-cred-code">{display}</code>
        {secret && value ? (
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            className="devices-icon-btn"
            title={revealed ? "Hide" : "Show"}
          >
            {revealed ? <EyeSlash size={14} /> : <Eye size={14} />}
          </button>
        ) : null}
        {value ? (
          <button
            type="button"
            onClick={copy}
            className="devices-icon-btn"
            title="Copy"
          >
            <Copy size={14} />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default function DeviceDetailPage() {
  const { id } = useParams();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const device = useAppSelector(selectDeviceById(id));
  const groups = useAppSelector(selectDeviceGroups);
  const allDevices = useAppSelector(selectDevices);
  const latestTelemetry = useAppSelector(selectLatest(id));

  const [label, setLabel] = useState("");
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";
  const [rpcTarget, setRpcTarget] = useState("");
  const [rpcType, setRpcType] = useState("on");
  const [rpcValue, setRpcValue] = useState("128");
  const [rpcSending, setRpcSending] = useState(false);

  const setTab = (tab) => setSearchParams({ tab }, { replace: true });

  useEffect(() => {
    if (!device && allDevices.length === 0) dispatch(fetchDevices());
  }, [dispatch, device, allDevices.length]);

  useEffect(() => {
    dispatch(fetchDeviceGroups());
  }, [dispatch]);

  useEffect(() => {
    let active = true;
    if (!device && id) {
      setLoading(true);
      getDevice(id)
        .then((d) => { if (active) dispatch(upsertDevice(d)); })
        .catch((err) => { if (active) toast.error(extractApiError(err).message); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (device) {
      setLabel(device.label || "");
      setGroupId(device.group_id || "");
    }
  }, [device]);

  useDashboardTelemetry(device ? [device.id] : []);
  const eventLog = useDeviceEventLog(device?.id);

  const onSaveDetails = async () => {
    setSaving(true);
    try {
      await dispatch(saveDevice({ id: device.id, changes: { label: label.trim() || null, groupId: groupId || null } })).unwrap();
      toast.success("Device updated");
    } catch (err) { toast.error(err?.message || "Failed to update"); }
    finally { setSaving(false); }
  };

  const onToggleMaintenance = async (next) => {
    try {
      await dispatch(saveDevice({ id: device.id, changes: { maintenanceMode: next } })).unwrap();
      toast.success(next ? "Maintenance ON" : "Maintenance OFF");
    } catch (err) { toast.error(err?.message || "Failed"); }
  };

  const onDelete = async () => {
    setDeleting(true);
    try {
      await dispatch(removeDevice(device.id)).unwrap();
      toast.success("Device deleted");
      navigate("/devices");
    } catch (err) {
      toast.error(err?.message || "Failed");
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const dirty = device
    ? label !== (device.label || "") || groupId !== (device.group_id || "")
    : false;
  const telemetryData = latestTelemetry?.data || {};
  const telemetryKeys = Object.keys(telemetryData);

  const attributes = useMemo(() => {
    if (!device) return [];
    const groupLabel = groups.find((g) => g.id === device.group_id)?.name;
    return [
      ["Device ID", device.id],
      ["UID", device.device_uid || "—"],
      ["Label", device.label || "—"],
      ["Status", device.status],
      ["Group", groupLabel || "—"],
      ["Firmware", device.firmware_version || "—"],
      ["Maintenance", device.maintenance_mode ? "Yes" : "No"],
      ["Simulator", device.is_simulator ? "Yes" : "No"],
      ["Org ID", device.org_id || "—"],
      ["MQTT node", device.node_id || "—"],
      ["Template", device.template_id || "—"],
    ];
  }, [device, groups]);

  const sendRpc = async () => {
    if (!device) return;
    setRpcSending(true);
    try {
      const body = { type: rpcType, target: rpcTarget || undefined };
      if (rpcType === "value") body.value = Number(rpcValue);
      await issueCommand(device.id, body);
      toast.success("RPC command sent");
    } catch (err) {
      toast.error(extractApiError(err).message || "RPC failed");
    } finally {
      setRpcSending(false);
    }
  };

  if (loading && !device) {
    return (
      <div className="devices-screen flex justify-center py-20">
        <CircleNotch size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!device) {
    return (
      <div className="devices-screen">
        <div className="devices-empty mx-auto max-w-md">
          <span className="devices-empty-icon">
            <Cpu size={28} weight="duotone" />
          </span>
          <h1 className="mt-4 text-lg font-semibold">Device not found</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            This device may have been deleted or you may not have access.
          </p>
          <Button className="mt-5" variant="outline" onClick={() => navigate("/devices")}>
            <ArrowLeft size={16} /> Back to devices
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="devices-screen">
      <header className="devices-hero">
        <div className="devices-hero-grid" aria-hidden />
        <div className="devices-hero-inner">
          <div className="flex min-w-0 items-start gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="mt-0.5 shrink-0"
              onClick={() => navigate("/devices")}
              aria-label="Back to devices"
            >
              <ArrowLeft size={18} />
            </Button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
                    device.status === "online"
                      ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  <Cpu size={22} weight="duotone" />
                </span>
                <div className="min-w-0">
                  <h1 className="truncate text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                    {device.label || device.device_uid || "Device"}
                  </h1>
                  <p className="truncate font-mono text-xs text-muted-foreground">
                    UID: {device.device_uid}
                    {device.firmware_version ? ` · FW ${device.firmware_version}` : ""}
                  </p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                    device.status === "online"
                      ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  <span
                    className={cn(
                      "devices-status-dot",
                      device.status === "online"
                        ? "devices-status-dot-online"
                        : "devices-status-dot-offline"
                    )}
                  />
                  {device.status === "online" ? "Online" : "Offline"}
                </span>
                {device.maintenance_mode ? (
                  <Badge variant="warning">
                    <Wrench size={11} /> Maintenance
                  </Badge>
                ) : null}
                {device.status === "online" ? (
                  <span className="devices-chip">
                    <PlugsConnected size={12} className="text-emerald-500" /> Live stream
                  </span>
                ) : (
                  <span className="devices-chip">
                    <Plugs size={12} /> No live stream
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setRechargeOpen(true)}>
              <CreditCard size={14} /> Recharge
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(true)}>
              <Trash size={14} /> Delete
            </Button>
          </div>
        </div>
      </header>

      <div className="mt-4">
        <EntityTabs tabs={DEVICE_TABS} active={activeTab} onChange={setTab} />
      </div>

      {activeTab === "overview" ? (
        <div className="devices-tab-panel grid gap-4 lg:grid-cols-3">
          <div className="space-y-4">
            <section className="devices-panel">
              <header className="devices-panel-head">
                <div className="devices-panel-title">
                  <Plugs size={16} className="text-primary" />
                  Connection info
                </div>
              </header>
              <div className="devices-panel-body space-y-4">
                <CredentialField label="Device Token" value={device.device_token} secret />
                <CredentialField label="Server" value="mqtt://your-server:1883" />
                <CredentialField
                  label="Telemetry Topic"
                  value={`iotaps/${device.org_id}/${device.id}/telemetry`}
                />
                <CredentialField
                  label="Command Topic"
                  value={`iotaps/${device.org_id}/${device.id}/command`}
                />
              </div>
            </section>
            <section className="devices-panel">
              <header className="devices-panel-head">
                <div className="devices-panel-title">QR code</div>
              </header>
              <div className="devices-panel-body">
                <QrDisplay deviceId={device.id} className="mx-auto" />
              </div>
            </section>
          </div>
          <div className="space-y-4 lg:col-span-2">
            <DeviceExplorer device={device} telemetryData={telemetryData} />
            <section className="devices-panel">
              <header className="devices-panel-head">
                <div className="devices-panel-title">
                  <SlidersHorizontal size={16} className="text-primary" />
                  Settings
                </div>
              </header>
              <div className="devices-panel-body space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Label</Label>
                    <Input
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      className="h-9 text-sm"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Group</Label>
                    <select
                      value={groupId}
                      onChange={(e) => setGroupId(e.target.value)}
                      className="devices-select h-9 w-full"
                    >
                      <option value="">No group</option>
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>{g.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border bg-muted/25 px-3 py-2.5">
                  <div>
                    <Label className="text-sm">Maintenance mode</Label>
                    <p className="text-xs text-muted-foreground">
                      Pause alerts and mark this device as intentionally down.
                    </p>
                  </div>
                  <Switch checked={device.maintenance_mode} onChange={onToggleMaintenance} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={onSaveDetails} disabled={!dirty || saving}>
                    <FloppyDisk size={14} /> Save
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setAssignOpen(true)}>
                    <UserPlus size={14} /> Assign user
                  </Button>
                </div>
              </div>
            </section>
          </div>
        </div>
      ) : null}

      {activeTab === "telemetry" ? (
        <section className="devices-panel devices-tab-panel">
          <header className="devices-panel-head">
            <div className="devices-panel-title">
              <Lightning size={16} className="text-primary" />
              Latest telemetry
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                onClick={async () => {
                  try {
                    await exportTelemetryCsv(device.id, { resolution: "raw" });
                    toast.success("Telemetry exported");
                  } catch {
                    toast.error("Export failed");
                  }
                }}
              >
                <DownloadSimple size={14} /> Export CSV
              </Button>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {device.status === "online" ? (
                  <PlugsConnected size={13} className="text-emerald-500" />
                ) : (
                  <Plugs size={13} />
                )}
                {device.status === "online" ? "Live" : "Offline"}
              </span>
            </div>
          </header>
          <div className="devices-panel-body">
            {telemetryKeys.length === 0 ? (
              <div className="devices-empty border-0">
                <span className="devices-empty-icon">
                  <Lightning size={26} weight="duotone" />
                </span>
                <h2 className="mt-3 text-sm font-semibold">No telemetry yet</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Values will appear here once this device publishes.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {telemetryKeys.map((key) => (
                  <div
                    key={key}
                    className="rounded-xl border border-border bg-muted/25 px-3.5 py-3"
                  >
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {key}
                    </div>
                    <div className="mt-1.5 text-xl font-bold tabular-nums text-foreground">
                      {String(telemetryData[key])}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "attributes" ? (
        <section className="devices-panel devices-tab-panel">
          <header className="devices-panel-head">
            <div className="devices-panel-title">
              <MagnifyingGlass size={16} className="text-primary" />
              Attributes
            </div>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="border-b border-border px-5 py-3 font-medium">Key</th>
                  <th className="border-b border-border px-5 py-3 font-medium">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {attributes.map(([k, v]) => (
                  <tr key={k} className="hover:bg-muted/25">
                    <td className="px-5 py-2.5 font-medium text-muted-foreground">{k}</td>
                    <td className="px-5 py-2.5 font-mono text-sm">{String(v)}</td>
                  </tr>
                ))}
                {telemetryKeys.map((key) => (
                  <tr key={`tel-${key}`} className="hover:bg-muted/25">
                    <td className="px-5 py-2.5 font-medium text-muted-foreground">
                      telemetry.{key}
                    </td>
                    <td className="px-5 py-2.5 font-mono text-sm">
                      {String(telemetryData[key])}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeTab === "events" ? (
        <section className="devices-panel devices-tab-panel">
          <header className="devices-panel-head">
            <div className="devices-panel-title">
              <ClockCounterClockwise size={16} className="text-primary" />
              Events
            </div>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="border-b border-border px-5 py-3 font-medium">Time</th>
                  <th className="border-b border-border px-5 py-3 font-medium">Kind</th>
                  <th className="border-b border-border px-5 py-3 font-medium">Event</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {eventLog.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-5 py-12 text-center">
                      <div className="devices-empty border-0 py-6">
                        <span className="devices-empty-icon">
                          <ClockCounterClockwise size={24} weight="duotone" />
                        </span>
                        <p className="mt-3 text-sm text-muted-foreground">
                          Listening for status, telemetry, commands, and alerts…
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  eventLog.map((ev, i) => (
                    <tr key={`${ev.ts}-${i}`} className="hover:bg-muted/25">
                      <td className="whitespace-nowrap px-5 py-2.5 text-xs text-muted-foreground">
                        {new Date(ev.ts).toLocaleString()}
                      </td>
                      <td className="px-5 py-2.5">
                        <Badge variant="outline">{ev.kind || "event"}</Badge>
                      </td>
                      <td className="px-5 py-2.5 text-sm">{ev.message}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeTab === "commands" ? (
        <div className="devices-tab-panel space-y-4">
          <section className="devices-panel">
            <header className="devices-panel-head">
              <div className="devices-panel-title">
                <Lightning size={16} className="text-primary" />
                Quick controls
              </div>
            </header>
            <div className="devices-panel-body space-y-4">
              <ToggleControl
                deviceId={device.id}
                deviceLabel={device.label || device.device_uid}
                label="Relay / Power"
              />
              <SliderControl
                deviceId={device.id}
                deviceLabel={device.label || device.device_uid}
                label="PWM level"
                min={0}
                max={255}
              />
            </div>
          </section>
          <section className="devices-panel">
            <header className="devices-panel-head">
              <div className="devices-panel-title">
                <Broadcast size={16} className="text-primary" />
                RPC / custom command
              </div>
            </header>
            <div className="devices-panel-body grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Target (optional)</Label>
                <Input
                  value={rpcTarget}
                  onChange={(e) => setRpcTarget(e.target.value)}
                  placeholder="e.g. relay1"
                  className="h-9 text-sm"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Type</Label>
                <select
                  value={rpcType}
                  onChange={(e) => setRpcType(e.target.value)}
                  className="devices-select h-9 w-full"
                >
                  <option value="on">on</option>
                  <option value="off">off</option>
                  <option value="value">value</option>
                </select>
              </div>
              {rpcType === "value" ? (
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-xs">Value</Label>
                  <Input
                    value={rpcValue}
                    onChange={(e) => setRpcValue(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
              ) : null}
              <div className="sm:col-span-2">
                <Button size="sm" onClick={sendRpc} disabled={rpcSending}>
                  {rpcSending ? "Sending…" : "Send RPC"}
                </Button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      <AssignUserDialog open={assignOpen} onClose={() => setAssignOpen(false)} device={device} />

      <Dialog
        open={confirmDelete}
        onClose={() => !deleting && setConfirmDelete(false)}
        title="Delete device?"
        description={`"${device.label || device.device_uid}" will be permanently removed.`}
      >
        <DialogBody className="text-sm text-muted-foreground">
          MQTT credentials will be revoked. This cannot be undone.
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => setConfirmDelete(false)} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onDelete} disabled={deleting}>
            <Trash size={14} /> {deleting ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </Dialog>

      <Dialog
        open={rechargeOpen}
        onClose={() => setRechargeOpen(false)}
        title="Recharge Device"
        description={`Extend Pro plan for "${device.label || device.device_uid}"`}
      >
        <DialogBody className="space-y-4">
          <div className="space-y-2 rounded-xl border border-border bg-muted/30 p-4">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Device</span>
              <span className="font-medium">{device.label || device.device_uid}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Plan</span>
              <span className="font-medium">Pro (per-device)</span>
            </div>
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Billing cycle</Label>
            <select className="devices-select h-9 w-full">
              <option value="monthly">Monthly — ₹99/device/month</option>
              <option value="yearly">Yearly — ₹999/device/year (save 16%)</option>
            </select>
          </div>
          <p className="text-xs text-muted-foreground">
            Payment will be processed via Razorpay. The subscription activates immediately for this device.
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => setRechargeOpen(false)}>Cancel</Button>
          <Button
            onClick={() => {
              toast.success("Redirecting to payment...");
              setRechargeOpen(false);
            }}
          >
            <CreditCard size={14} /> Pay & Activate
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  );
}
