import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
  Lightning,
  CreditCard,
  Plugs,
  PlugsConnected,
  ArrowsClockwise,
  Broadcast,
  CaretRight,
  CaretDown,
  Circle,
  DownloadSimple,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDevices,
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

// Per-device MQTT Explorer — tree structure with folder/file icons
function DeviceExplorer({ device, telemetryData }) {
  const [expanded, setExpanded] = useState({ telemetry: true, command: false, ack: false, status: true });
  const token = device.device_token || device.device_uid || device.id;
  const baseTopic = `iotaps/${token}`;

  const toggle = (key) => setExpanded((e) => ({ ...e, [key]: !e[key] }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Broadcast size={16} className="text-primary" />
          <CardTitle className="text-sm">MQTT Explorer</CardTitle>
          <Badge variant="muted" className="text-[9px]">4 topics</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="border-t border-border bg-card font-mono text-xs">
          {/* Root */}
          <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-3 py-2">
            <span className="text-base">🌐</span>
            <span className="font-semibold text-foreground">{baseTopic}</span>
          </div>

          {/* /telemetry */}
          <div className="border-b border-border/30">
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors" onClick={() => toggle("telemetry")}>
              <span className="w-4 text-center">{expanded.telemetry ? "📂" : "📁"}</span>
              <span className="font-medium text-foreground">/telemetry</span>
              <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600">↑ PUBLISH</span>
            </div>
            {expanded.telemetry && (
              <div className="bg-muted/10 px-3 pb-2 pl-9 space-y-1">
                <div className="text-[10px] text-muted-foreground pb-1">Device sends sensor data here every 5s</div>
                {Object.keys(telemetryData).length > 0 ? (
                  Object.entries(telemetryData).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 py-0.5">
                      <span className="text-[11px]">📄</span>
                      <span className="text-muted-foreground">{k}</span>
                      <span className="text-primary font-bold">{JSON.stringify(v)}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-muted-foreground italic">Waiting for data...</div>
                )}
              </div>
            )}
          </div>

          {/* /command */}
          <div className="border-b border-border/30">
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors" onClick={() => toggle("command")}>
              <span className="w-4 text-center">{expanded.command ? "📂" : "📁"}</span>
              <span className="font-medium text-foreground">/command</span>
              <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600">↓ SUBSCRIBE</span>
            </div>
            {expanded.command && (
              <div className="bg-muted/10 px-3 pb-2 pl-9 space-y-1">
                <div className="text-[10px] text-muted-foreground pb-1">Device listens here for remote commands</div>
                <div className="flex items-center gap-2 py-0.5">
                  <span className="text-[11px]">📄</span>
                  <span className="text-muted-foreground">Format:</span>
                  <code className="text-primary">{"{"}"type","target","value","command_id"{"}"}</code>
                </div>
              </div>
            )}
          </div>

          {/* /ack */}
          <div className="border-b border-border/30">
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors" onClick={() => toggle("ack")}>
              <span className="w-4 text-center">{expanded.ack ? "📂" : "📁"}</span>
              <span className="font-medium text-foreground">/ack</span>
              <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600">↑ PUBLISH</span>
            </div>
            {expanded.ack && (
              <div className="bg-muted/10 px-3 pb-2 pl-9 space-y-1">
                <div className="text-[10px] text-muted-foreground pb-1">Device confirms command execution</div>
                <div className="flex items-center gap-2 py-0.5">
                  <span className="text-[11px]">📄</span>
                  <span className="text-muted-foreground">Format:</span>
                  <code className="text-primary">{"{"}"command_id","status":"executed"{"}"}</code>
                </div>
              </div>
            )}
          </div>

          {/* /status */}
          <div>
            <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-accent/30 transition-colors" onClick={() => toggle("status")}>
              <span className="w-4 text-center">{expanded.status ? "📂" : "📁"}</span>
              <span className="font-medium text-foreground">/status</span>
              <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600">LWT</span>
            </div>
            {expanded.status && (
              <div className="bg-muted/10 px-3 pb-2 pl-9 space-y-1">
                <div className="text-[10px] text-muted-foreground pb-1">Last Will & Testament (auto offline detection)</div>
                <div className="flex items-center gap-2 py-0.5">
                  <span className="text-[11px]">{device.status === "online" ? "🟢" : "🔴"}</span>
                  <span className="font-bold text-foreground">{device.status}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Credential display with copy + reveal
function CredentialField({ label, value, secret }) {
  const [revealed, setRevealed] = useState(false);
  const display = secret && !revealed ? "••••••••••••" : (value || "—");

  const copy = () => {
    if (!value) return;
    navigator.clipboard.writeText(value);
    toast.success(`${label} copied`);
  };

  return (
    <div className="space-y-1">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <code className="flex-1 truncate rounded bg-muted px-2 py-1 text-xs font-mono">
          {display}
        </code>
        {secret && value && (
          <button onClick={() => setRevealed(!revealed)} className="text-muted-foreground hover:text-foreground" title={revealed ? "Hide" : "Show"}>
            {revealed ? <EyeSlash size={14} /> : <Eye size={14} />}
          </button>
        )}
        {value && (
          <button onClick={copy} className="text-muted-foreground hover:text-foreground" title="Copy">
            <Copy size={14} />
          </button>
        )}
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

  useEffect(() => {
    if (!device && allDevices.length === 0) dispatch(fetchDevices());
  }, [dispatch, device, allDevices.length]);

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

  if (loading && !device) {
    return <div className="flex justify-center py-20"><CircleNotch size={24} className="animate-spin text-muted-foreground" /></div>;
  }

  if (!device) {
    return (
      <section className="mx-auto max-w-2xl space-y-3 p-8 text-center">
        <h1 className="text-xl font-semibold">Device not found</h1>
        <Button variant="outline" onClick={() => navigate("/devices")}><ArrowLeft size={16} /> Back</Button>
      </section>
    );
  }

  const dirty = label !== (device.label || "") || groupId !== (device.group_id || "");
  const telemetryData = latestTelemetry?.data || {};
  const telemetryKeys = Object.keys(telemetryData);

  return (
    <section className="mx-auto max-w-6xl space-y-4 px-2">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/devices")}><ArrowLeft size={18} /></Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold">{device.label || device.device_uid || "Device"}</h1>
              <Badge variant={device.status === "online" ? "success" : "muted"}>{device.status}</Badge>
              {device.maintenance_mode && <Badge variant="warning">Maintenance</Badge>}
            </div>
            <p className="text-xs text-muted-foreground">UID: {device.device_uid} • Firmware: {device.firmware_version || "—"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setRechargeOpen(true)}>
            <CreditCard size={14} /> Recharge
          </Button>
          <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(true)}>
            <Trash size={14} /> Delete
          </Button>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left Column — Connection + QR */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Connection Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <CredentialField label="Device Token" value={device.device_token} secret />
              <CredentialField label="Server" value="mqtt://your-server:1883" />
              <CredentialField label="Telemetry Topic" value={`iotaps/${device.org_id}/${device.id}/telemetry`} />
              <CredentialField label="Command Topic" value={`iotaps/${device.org_id}/${device.id}/command`} />
              <p className="text-[10px] text-muted-foreground">Use the Device Token as both MQTT username and password</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">QR Code</CardTitle>
            </CardHeader>
            <CardContent>
              <QrDisplay deviceId={device.id} className="mx-auto" />
            </CardContent>
          </Card>
        </div>

        {/* Center Column — Explorer + Live Telemetry + Controls */}
        <div className="space-y-4 lg:col-span-2">
          {/* Per-device MQTT Explorer */}
          <DeviceExplorer device={device} telemetryData={telemetryData} />

          {/* Live Telemetry */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Live Telemetry</CardTitle>
                <div className="flex items-center gap-3">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
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
                  <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    {device.status === "online" ? <PlugsConnected size={12} className="text-emerald-500" /> : <Plugs size={12} />}
                    {device.status === "online" ? "Receiving" : "Offline"}
                  </span>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {telemetryKeys.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">No telemetry data yet. Connect your device to see live values.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {telemetryKeys.map((key) => (
                    <div key={key} className="rounded-lg border border-border bg-muted/30 px-3 py-2">
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{key}</div>
                      <div className="text-lg font-bold tabular-nums">{String(telemetryData[key])}</div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Controls */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Device Controls</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <ToggleControl deviceId={device.id} deviceLabel={device.label || device.device_uid} label="Relay / Power" />
              <SliderControl deviceId={device.id} deviceLabel={device.label || device.device_uid} label="PWM Level" min={0} max={255} />
            </CardContent>
          </Card>

          {/* Settings */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-xs">Label</Label>
                  <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={device.device_uid} className="h-8 text-sm" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Group</Label>
                  <select value={groupId} onChange={(e) => setGroupId(e.target.value)} className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm">
                    <option value="">No group</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Maintenance mode</Label>
                <Switch checked={device.maintenance_mode} onChange={onToggleMaintenance} />
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={onSaveDetails} disabled={!dirty || saving}>
                  <FloppyDisk size={14} /> {saving ? "Saving..." : "Save"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setAssignOpen(true)}>
                  <UserPlus size={14} /> Assign user
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Assign user dialog */}
      <AssignUserDialog open={assignOpen} onClose={() => setAssignOpen(false)} device={device} />

      {/* Delete confirmation */}
      <Dialog open={confirmDelete} onClose={() => !deleting && setConfirmDelete(false)} title="Delete device?" description={`"${device.label || device.device_uid}" will be permanently removed.`}>
        <DialogBody className="text-sm text-muted-foreground">MQTT credentials will be revoked. This cannot be undone.</DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</Button>
          <Button variant="destructive" onClick={onDelete} disabled={deleting}><Trash size={14} /> {deleting ? "Deleting..." : "Delete"}</Button>
        </DialogFooter>
      </Dialog>

      {/* Single device recharge dialog */}
      <Dialog open={rechargeOpen} onClose={() => setRechargeOpen(false)} title="Recharge Device" description={`Extend Pro plan for "${device.label || device.device_uid}"`}>
        <DialogBody className="space-y-4">
          <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-2">
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
            <select className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
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
          <Button onClick={() => { toast.success("Redirecting to payment..."); setRechargeOpen(false); }}>
            <CreditCard size={14} /> Pay & Activate
          </Button>
        </DialogFooter>
      </Dialog>
    </section>
  );
}
