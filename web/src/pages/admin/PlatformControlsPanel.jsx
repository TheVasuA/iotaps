import { useState } from "react";
import { toast } from "sonner";
import { Lightning, Broom, ShieldWarning, Power } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import apiClient from "@/lib/apiClient";

export default function PlatformControlsPanel() {
  const [busy, setBusy] = useState(null);

  const action = async (name, fn) => {
    setBusy(name);
    try {
      await fn();
      toast.success(`${name} completed`);
    } catch (err) {
      toast.error(err?.response?.data?.message || `${name} failed`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Lightning size={20} className="text-amber-500" />
            Platform Controls
          </CardTitle>
          <CardDescription>
            Quick actions for platform maintenance and operations.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="text-sm font-medium">Flush Redis Cache</h3>
            <p className="text-xs text-muted-foreground">
              Clear all cached platform settings, telemetry, and sessions. Users will need to re-login.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="text-amber-600 border-amber-300 hover:bg-amber-50"
              disabled={busy === "flush"}
              onClick={() => action("flush", () => apiClient.post("/admin/platform/flush-cache"))}
            >
              <Broom size={14} className="mr-1" />
              {busy === "flush" ? "Flushing..." : "Flush Cache"}
            </Button>
          </div>

          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="text-sm font-medium">Maintenance Mode</h3>
            <p className="text-xs text-muted-foreground">
              Toggle platform-wide maintenance mode. API returns 503 to all non-admin requests.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="text-orange-600 border-orange-300 hover:bg-orange-50"
              disabled={busy === "maintenance"}
              onClick={() => action("maintenance", () => apiClient.post("/admin/platform/toggle-maintenance"))}
            >
              <ShieldWarning size={14} className="mr-1" />
              {busy === "maintenance" ? "Toggling..." : "Toggle Maintenance"}
            </Button>
          </div>

          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="text-sm font-medium">Force Disconnect All WS</h3>
            <p className="text-xs text-muted-foreground">
              Disconnect all WebSocket clients. They will auto-reconnect.
            </p>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "ws"}
              onClick={() => action("ws", () => apiClient.post("/admin/platform/disconnect-ws"))}
            >
              <Power size={14} className="mr-1" />
              {busy === "ws" ? "Disconnecting..." : "Disconnect All"}
            </Button>
          </div>

          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="text-sm font-medium">Trigger DB Backup</h3>
            <p className="text-xs text-muted-foreground">
              Create a pg_dump snapshot of the database (stored on VPS disk).
            </p>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "backup"}
              onClick={() => action("backup", () => apiClient.post("/admin/platform/backup"))}
            >
              {busy === "backup" ? "Backing up..." : "Backup Now"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
