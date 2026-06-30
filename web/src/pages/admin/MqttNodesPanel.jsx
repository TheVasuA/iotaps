import { useState } from "react";
import { toast } from "sonner";
import {
  HardDrives,
  Trash,
  Plus,
  Pause,
  Play,
  PencilSimple,
  FloppyDisk,
  PlugsConnected,
} from "@phosphor-icons/react";
import {
  getMqttNodes,
  registerMqttNode,
  deregisterMqttNode,
  updateMqttNode,
} from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

// Super_Admin MQTT node management & monitoring panel (Task 20.7, Req 24.1-24.4).
// Lists registered nodes with per-node RAM/CPU/disk + active connection metrics
// from GET /admin/mqtt-nodes, and lets the operator register (Req 24.1),
// deregister (Req 24.2), drain/enable, and resize (Req 24.4) nodes.

const DISABLED = "disabled";
const ACTIVE = "active";

function pct(value) {
  return value == null ? "—" : `${Number(value).toFixed(0)}%`;
}

function utilizationRatio(active, capacity) {
  if (!capacity) return 0;
  return Math.min(1, active / capacity);
}

function utilizationVariant(active, capacity) {
  const ratio = utilizationRatio(active, capacity);
  if (ratio >= 0.9) return "warning";
  if (ratio === 0) return "muted";
  return "success";
}

function NodeMetric({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-center">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

/** Thin capacity-utilization bar coloured by load. */
function UtilizationBar({ active, capacity }) {
  const ratio = utilizationRatio(active, capacity);
  const variant = utilizationVariant(active, capacity);
  const color =
    variant === "warning"
      ? "bg-amber-500"
      : variant === "muted"
        ? "bg-muted-foreground/30"
        : "bg-emerald-500";
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={Math.round(ratio * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Node utilization"
    >
      <div
        className={`h-full rounded-full transition-all ${color}`}
        style={{ width: `${Math.max(ratio * 100, active > 0 ? 4 : 0)}%` }}
      />
    </div>
  );
}

function FleetSummary({ nodes }) {
  const totalCapacity = nodes.reduce((s, n) => s + (n.capacity || 0), 0);
  const totalActive = nodes.reduce((s, n) => s + (n.active_connections || 0), 0);
  const activeNodes = nodes.filter((n) => n.status === ACTIVE).length;
  const drainedNodes = nodes.filter((n) => n.status === DISABLED).length;
  const tiles = [
    { label: "Nodes", value: nodes.length },
    { label: "Accepting", value: activeNodes },
    { label: "Drained", value: drainedNodes },
    {
      label: "Connections",
      value: `${totalActive.toLocaleString()} / ${totalCapacity.toLocaleString()}`,
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="bg-card px-4 py-3">
          <dt className="text-xs text-muted-foreground">{t.label}</dt>
          <dd className="mt-0.5 text-lg font-semibold text-foreground">
            {t.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function NodeCard({ node, onDrainToggle, onSaveCapacity, onDeregister }) {
  const [editing, setEditing] = useState(false);
  const [capacity, setCapacity] = useState(String(node.capacity));
  const [busy, setBusy] = useState(false);
  const drained = node.status === DISABLED;

  const saveCapacity = async () => {
    setBusy(true);
    try {
      await onSaveCapacity(node, Number(capacity));
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className={drained ? "opacity-80" : undefined}>
      <CardContent className="space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <HardDrives size={24} className="text-primary" />
            <div>
              <p className="font-medium text-foreground">
                {node.ip}:{node.port}
              </p>
              <p className="text-xs text-muted-foreground">{node.id}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={utilizationVariant(
                node.active_connections,
                node.capacity
              )}
            >
              <PlugsConnected size={12} className="mr-1" />
              {node.active_connections}/{node.capacity}
            </Badge>
            <Badge variant={drained ? "warning" : "success"}>
              {drained ? "Drained" : "Accepting"}
            </Badge>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onDrainToggle(node)}
              title={
                drained
                  ? "Re-enable: route new devices to this node"
                  : "Drain: stop assigning new devices (keeps existing connections)"
              }
            >
              {drained ? <Play size={16} /> : <Pause size={16} />}
              <span className="hidden sm:inline">
                {drained ? "Enable" : "Drain"}
              </span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onDeregister(node.id)}
              aria-label={`Deregister node ${node.ip}`}
            >
              <Trash size={16} />
            </Button>
          </div>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Capacity utilization</span>
            {editing ? (
              <span className="flex items-center gap-1.5">
                <Input
                  type="number"
                  min={node.active_connections || 1}
                  value={capacity}
                  onChange={(e) => setCapacity(e.target.value)}
                  className="h-7 w-24"
                  aria-label="Edit capacity"
                />
                <Button
                  type="button"
                  size="sm"
                  className="h-7 px-2"
                  disabled={busy || !capacity}
                  onClick={saveCapacity}
                >
                  <FloppyDisk size={14} />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2"
                  onClick={() => {
                    setEditing(false);
                    setCapacity(String(node.capacity));
                  }}
                >
                  Cancel
                </Button>
              </span>
            ) : (
              <button
                type="button"
                className="inline-flex items-center gap-1 hover:text-foreground"
                onClick={() => setEditing(true)}
              >
                <PencilSimple size={12} />
                Edit capacity
              </button>
            )}
          </div>
          <UtilizationBar
            active={node.active_connections}
            capacity={node.capacity}
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <NodeMetric label="RAM" value={pct(node.ram_pct)} />
          <NodeMetric label="CPU" value={pct(node.cpu_pct)} />
          <NodeMetric label="Disk" value={pct(node.disk_pct)} />
        </div>
      </CardContent>
    </Card>
  );
}

export default function MqttNodesPanel() {
  const { data, status, error, reload } = useAdminData(getMqttNodes);
  const nodes = data ?? [];

  const [ip, setIp] = useState("");
  const [port, setPort] = useState("1883");
  const [capacity, setCapacity] = useState("1000");
  const [busy, setBusy] = useState(false);

  const onRegister = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await registerMqttNode({
        ip: ip.trim(),
        port: Number(port),
        capacity: Number(capacity),
      });
      toast.success("MQTT node registered");
      setIp("");
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const onDeregister = async (nodeId) => {
    try {
      await deregisterMqttNode(nodeId);
      toast.success("MQTT node deregistered");
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const onDrainToggle = async (node) => {
    const next = node.status === DISABLED ? ACTIVE : DISABLED;
    try {
      await updateMqttNode(node.id, { status: next });
      toast.success(
        next === DISABLED
          ? "Node drained — no new devices will be assigned"
          : "Node re-enabled for device assignment"
      );
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const onSaveCapacity = async (node, newCapacity) => {
    try {
      await updateMqttNode(node.id, { capacity: newCapacity });
      toast.success("Node capacity updated");
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
      throw err;
    }
  };

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Plus size={20} className="text-primary" />
            Register node
          </CardTitle>
          <CardDescription>
            Add an MQTT (Mosquitto) node so it is eligible for device assignment
            (Req 24.1).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-3" onSubmit={onRegister}>
            <div className="space-y-1.5">
              <Label htmlFor="node-ip">IP / host</Label>
              <Input
                id="node-ip"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="10.0.0.5"
                required
              />
            </div>
            <div className="w-28 space-y-1.5">
              <Label htmlFor="node-port">Port</Label>
              <Input
                id="node-port"
                type="number"
                min={1}
                max={65535}
                value={port}
                onChange={(e) => setPort(e.target.value)}
                required
              />
            </div>
            <div className="w-32 space-y-1.5">
              <Label htmlFor="node-capacity">Capacity</Label>
              <Input
                id="node-capacity"
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={busy || !ip.trim()}>
              Register
            </Button>
          </form>
        </CardContent>
      </Card>

      <AdminPanel status={status} error={error}>
        {nodes.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
            No MQTT nodes registered yet.
          </div>
        ) : (
          <div className="space-y-4">
            <FleetSummary nodes={nodes} />
            {nodes.map((node) => (
              <NodeCard
                key={node.id}
                node={node}
                onDrainToggle={onDrainToggle}
                onSaveCapacity={onSaveCapacity}
                onDeregister={onDeregister}
              />
            ))}
          </div>
        )}
      </AdminPanel>
    </section>
  );
}
