import { useState } from "react";
import { toast } from "sonner";
import { HardDrives, Trash, Plus } from "@phosphor-icons/react";
import {
  getMqttNodes,
  registerMqttNode,
  deregisterMqttNode,
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

// Super_Admin MQTT node management & monitoring panel (Task 20.7, Req 24.1-24.3).
// Lists registered nodes with per-node RAM/CPU/disk + active connection metrics
// from GET /admin/mqtt-nodes, and lets the operator register (Req 24.1) or
// deregister (Req 24.2) nodes.

function pct(value) {
  return value == null ? "—" : `${Number(value).toFixed(0)}%`;
}

function utilizationVariant(active, capacity) {
  if (!capacity) return "muted";
  const ratio = active / capacity;
  if (ratio >= 0.9) return "warning";
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
            {nodes.map((node) => (
              <Card key={node.id}>
                <CardContent className="space-y-4 p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <HardDrives size={24} className="text-primary" />
                      <div>
                        <p className="font-medium text-foreground">
                          {node.ip}:{node.port}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {node.id}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={utilizationVariant(
                          node.active_connections,
                          node.capacity
                        )}
                      >
                        {node.active_connections}/{node.capacity} conns
                      </Badge>
                      {node.status ? (
                        <Badge variant="outline">{node.status}</Badge>
                      ) : null}
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
                  <div className="grid grid-cols-3 gap-3">
                    <NodeMetric label="RAM" value={pct(node.ram_pct)} />
                    <NodeMetric label="CPU" value={pct(node.cpu_pct)} />
                    <NodeMetric label="Disk" value={pct(node.disk_pct)} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </AdminPanel>
    </section>
  );
}
