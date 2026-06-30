import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ShieldWarning,
  HardDrives,
  DownloadSimple,
  ArrowClockwise,
  Warning,
  CheckCircle,
  XCircle,
  Database,
} from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import apiClient from "@/lib/apiClient";
import { getHealth, getSystemStats, getMqttNodes, getVaultStatus, syncVault } from "@/lib/adminApi";

// Disaster Recovery / Failover panel (Req 28-29, ops).
//
// IMPORTANT: this single-VPS deployment has NO automatic failover. If the VPS
// itself goes down, the platform is offline until manual recovery. This panel
// surfaces what CAN be done from inside the app while the server is alive:
//   1. Early-warning health (disk-full + RAM exhaustion are the top crash causes)
//   2. One-click emergency backup download (off-box copy of all data)
//   3. MQTT node failover status (a standby broker node can absorb connections)
//   4. The exact recovery runbook, shown inline so on-call never has to guess.

function pct(used, total) {
  if (!total) return 0;
  return Math.round((used / total) * 100);
}

function StatusDot({ ok }) {
  return ok ? (
    <CheckCircle size={16} weight="fill" className="text-emerald-500" />
  ) : (
    <XCircle size={16} weight="fill" className="text-red-500" />
  );
}

function Meter({ label, percent, danger = 80 }) {
  const critical = percent >= danger;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className={critical ? "font-semibold text-red-600" : "font-medium"}>{percent}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted">
        <div
          className={`h-2 rounded-full ${critical ? "bg-red-500" : percent >= 60 ? "bg-amber-500" : "bg-emerald-500"}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
}

export default function DisasterRecoveryPanel() {
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [vault, setVault] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [h, s, n, v] = await Promise.allSettled([
        getHealth(),
        getSystemStats(),
        getMqttNodes(),
        getVaultStatus(),
      ]);
      if (h.status === "fulfilled") setHealth(h.value);
      if (s.status === "fulfilled") setStats(s.value);
      if (n.status === "fulfilled") setNodes(n.value || []);
      if (v.status === "fulfilled") setVault(v.value);
    } catch {
      toast.error("Failed to load recovery status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

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
      toast.success("Emergency backup downloaded — store it off-server");
    } catch (err) {
      toast.error(err?.response?.data?.message || "Backup failed");
    } finally {
      setBusy(null);
    }
  };

  const handleVaultSync = async () => {
    setBusy("vault");
    try {
      const res = await syncVault();
      const s = res?.synced || {};
      toast.success(
        `Vault synced — ${s.users || 0} users, ${s.device_credentials || 0} credentials, ${s.devices || 0} devices`
      );
      const v = await getVaultStatus();
      setVault(v);
    } catch (err) {
      toast.error(err?.response?.data?.message || "Vault sync failed");
    } finally {
      setBusy(null);
    }
  };

  const ram = stats?.ram || {};
  const disk = stats?.disk || {};
  const ramPct = ram.percent ?? pct(ram.used, ram.total);
  const diskPct = disk.percent ?? pct(disk.used, disk.total);
  const connections = stats?.mqtt_connections ?? 0;
  const maxConn = stats?.max_connections_design ?? 10000;
  const activeNodes = nodes.filter((n) => (n.status || "active") === "active");
  const hasStandby = activeNodes.length > 1;

  return (
    <div className="space-y-6">
      {/* Reality banner */}
      <Card className="border-amber-300">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2 text-amber-600">
            <ShieldWarning size={20} />
            Disaster Recovery &amp; Failover
          </CardTitle>
          <CardDescription>
            This platform runs on a single VPS. There is <strong>no automatic failover</strong> if
            the server itself goes down. Use this panel to watch for warning signs, keep an
            off-server backup, and follow the recovery runbook if a crash happens.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={loading} onClick={refresh}>
              <ArrowClockwise size={14} className={`mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh status
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-emerald-600 border-emerald-300 hover:bg-emerald-50"
              disabled={busy === "backup"}
              onClick={handleBackupDownload}
            >
              <DownloadSimple size={14} className="mr-1" />
              {busy === "backup" ? "Backing up..." : "Emergency Backup & Download"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Early-warning health */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Early-warning health</CardTitle>
          <CardDescription>
            Disk-full and RAM exhaustion are the most common causes of a crash. Act before these
            hit 100%.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-4">
            <Meter label="Disk usage" percent={diskPct} danger={85} />
            <Meter label="RAM usage" percent={ramPct} danger={85} />
            <div className="text-xs text-muted-foreground">
              MQTT connections:{" "}
              <span className="font-medium text-foreground">
                {connections.toLocaleString()} / {maxConn.toLocaleString()}
              </span>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">Services</p>
            <div className="space-y-1">
              {(health?.services || []).map((svc) => (
                <div key={svc.name} className="flex items-center gap-2 text-sm">
                  <StatusDot ok={svc.status === "ok"} />
                  <span className="capitalize">{svc.name}</span>
                  <span className="text-xs text-muted-foreground">({svc.status})</span>
                </div>
              ))}
              {!health && <p className="text-xs text-muted-foreground">Loading…</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Failover readiness */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <HardDrives size={18} />
            MQTT node failover readiness
          </CardTitle>
          <CardDescription>
            Registering a second MQTT node lets device load spread across boxes, so one broker
            failing does not drop every device.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm">
            {hasStandby ? (
              <>
                <CheckCircle size={16} weight="fill" className="text-emerald-500" />
                <span>
                  {activeNodes.length} active nodes — load can shift if one fails.
                </span>
              </>
            ) : (
              <>
                <Warning size={16} weight="fill" className="text-amber-500" />
                <span>
                  Only {activeNodes.length || 0} active node. No broker redundancy — add a standby
                  node under <strong>MQTT Nodes</strong>.
                </span>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Identity vault (MongoDB off-VPS mirror) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Database size={18} />
            Identity vault (MongoDB mirror)
          </CardTitle>
          <CardDescription>
            An off-VPS copy of critical identity data — user logins (with password hashes, never
            plaintext), device tokens, and device records — in MongoDB. Survives a full server loss
            and is independently queryable. Postgres stays the source of truth.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {vault && !vault.enabled && (
            <div className="flex items-center gap-2 text-sm">
              <Warning size={16} weight="fill" className="text-amber-500" />
              <span>
                Not configured. Set <code>MONGODB_URI</code> in <code>.env</code> to enable the
                off-VPS identity mirror.
              </span>
            </div>
          )}
          {vault && vault.enabled && (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                {vault.connected ? (
                  <>
                    <CheckCircle size={16} weight="fill" className="text-emerald-500" />
                    <span>Connected to {vault.database}</span>
                  </>
                ) : (
                  <>
                    <XCircle size={16} weight="fill" className="text-red-500" />
                    <span>Configured but not reachable — check the Atlas URI / IP allow-list.</span>
                  </>
                )}
              </div>
              {vault.counts && (
                <div className="text-xs text-muted-foreground">
                  Mirrored: {vault.counts.users ?? 0} users · {vault.counts.device_credentials ?? 0}{" "}
                  credentials · {vault.counts.devices ?? 0} devices
                </div>
              )}
            </div>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={busy === "vault" || (vault && !vault.enabled)}
            onClick={handleVaultSync}
          >
            <Database size={14} className="mr-1" />
            {busy === "vault" ? "Syncing..." : "Sync identity vault now"}
          </Button>
          <p className="text-[11px] text-muted-foreground">
            A background worker re-syncs automatically every few minutes; device changes mirror
            instantly. Use this for an on-demand sync.
          </p>
        </CardContent>
      </Card>

      {/* Recovery runbook */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">If the server crashes — recovery runbook</CardTitle>
          <CardDescription>
            Follow these in order. Keep a copy off the platform (it&apos;s on the server that may be
            down).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <p className="font-medium">1. Confirm scope</p>
            <p className="text-muted-foreground">
              Check the Contabo panel. If the VPS is up but a container died, it self-heals
              (<code>restart: always</code>). If the VPS is down, go to step 2.
            </p>
          </div>
          <div>
            <p className="font-medium">2. Restart the stack (VPS reachable)</p>
            <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-3 text-xs">
{`cd ~/projects/iotaps
docker compose ps          # see what's down
docker compose up -d       # bring everything back (never use -v)
docker logs iotaps-postgres --tail 50`}
            </pre>
          </div>
          <div>
            <p className="font-medium">3. Recover on a NEW VPS (original is dead)</p>
            <pre className="mt-1 overflow-x-auto rounded-md bg-muted p-3 text-xs">
{`# On a fresh Contabo VPS (see firmware/deploy.txt Part 3):
git clone https://github.com/TheVasuA/iotaps.git && cd iotaps
nano .env                          # paste saved secrets
docker compose up -d postgres
# restore the latest .dump you downloaded:
docker cp iotaps_backup_XXXX.dump iotaps-postgres:/tmp/r.dump
docker exec iotaps-postgres pg_restore --clean --if-exists -U iotaps -d iotaps /tmp/r.dump
docker compose up -d
docker exec -w /srv/app iotaps-api alembic upgrade head`}
            </pre>
          </div>
          <div>
            <p className="font-medium">4. Repoint devices &amp; DNS</p>
            <p className="text-muted-foreground">
              In Cloudflare DNS, update the <code>api</code> and <code>mqtt</code> A records to the
              new VPS IP. Devices reconnect automatically once DNS propagates (keep TTL low —
              60s — so failover is fast).
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Recommended permanent fix */}
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="text-base">Make it survive a server failure (recommended)</CardTitle>
          <CardDescription>
            True failover needs infrastructure beyond this one box. Options, cheapest first:
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">A. Warm standby (low cost).</strong> A second
            cheap VPS with the stack deployed and nightly DB restores. On failure, flip Cloudflare
            DNS to it. Minutes of downtime, near-zero data loss.
          </p>
          <p>
            <strong className="text-foreground">B. Managed DB + 2 app servers.</strong> Move
            Postgres to a managed/replicated database, run two app+broker VPSes behind a load
            balancer. Survives one box dying with no manual step.
          </p>
          <p>
            <strong className="text-foreground">C. Off-site backups (do this regardless).</strong>{" "}
            Automate the nightly <code>pg_dump</code> and push it to object storage (Cloudflare R2
            / S3). Without this, a dead disk loses everything.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
