import { useRef, useState } from "react";
import { toast } from "sonner";
import { Lightning, Broom, ShieldWarning, Power, DownloadSimple, UploadSimple } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import apiClient from "@/lib/apiClient";

export default function PlatformControlsPanel() {
  const [busy, setBusy] = useState(null);
  const restoreInputRef = useRef(null);

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

  // Download a fresh pg_dump backup straight to the admin's machine.
  const handleBackupDownload = async () => {
    setBusy("backup");
    try {
      const res = await apiClient.get("/admin/platform/backup/download", {
        responseType: "blob",
        timeout: 0,
      });
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "");
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `iotaps_backup_${stamp}.dump`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Backup downloaded");
    } catch (err) {
      toast.error(err?.response?.data?.message || "Backup failed");
    } finally {
      setBusy(null);
    }
  };

  // Restore from an uploaded .dump file (destructive - confirmed first).
  const handleRestoreFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file later
    if (!file) return;
    const ok = window.confirm(
      `Restore the database from "${file.name}"?\n\n` +
        "This OVERWRITES all current data (users, devices, telemetry) and cannot be undone."
    );
    if (!ok) return;

    setBusy("restore");
    try {
      const form = new FormData();
      form.append("file", file);
      await apiClient.post("/admin/platform/restore", form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 0,
      });
      toast.success("Database restored");
    } catch (err) {
      toast.error(err?.response?.data?.message || "Restore failed");
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

          <div className="rounded-lg border p-4 space-y-2 sm:col-span-2">
            <h3 className="text-sm font-medium">Backup &amp; Restore Database</h3>
            <p className="text-xs text-muted-foreground">
              Download a full pg_dump snapshot (users, devices, telemetry, billing) to your
              machine, or restore the database from a previously downloaded
              <code className="mx-1">.dump</code> file. Restore overwrites all current data.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                size="sm"
                variant="outline"
                className="text-emerald-600 border-emerald-300 hover:bg-emerald-50"
                disabled={busy === "backup"}
                onClick={handleBackupDownload}
              >
                <DownloadSimple size={14} className="mr-1" />
                {busy === "backup" ? "Backing up..." : "Backup & Download"}
              </Button>

              <Button
                size="sm"
                variant="outline"
                className="text-red-600 border-red-300 hover:bg-red-50"
                disabled={busy === "restore"}
                onClick={() => restoreInputRef.current?.click()}
              >
                <UploadSimple size={14} className="mr-1" />
                {busy === "restore" ? "Restoring..." : "Restore from File"}
              </Button>
              <input
                ref={restoreInputRef}
                type="file"
                accept=".dump,.sql"
                className="hidden"
                onChange={handleRestoreFile}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
