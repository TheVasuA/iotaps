import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Prohibit, ListChecks, Gear, Plus } from "@phosphor-icons/react";
import { getSecurity, getSettings, updateSettings } from "@/lib/adminApi";
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

// Super_Admin security & settings panel (Task 20.7, Req 29.2, 29.4). Surfaces
// login attempts, blocked IPs, and the audit log (GET /admin/security), plus a
// platform settings editor (GET/PATCH /admin/settings).

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function SecuritySection() {
  const { data, status, error } = useAdminData(() => getSecurity());
  const loginAttempts = data?.login_attempts ?? [];
  const blockedIps = data?.blocked_ips ?? [];
  const auditLog = data?.audit_log ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ShieldCheck size={20} className="text-primary" />
          Security
        </CardTitle>
        <CardDescription>
          Login attempts, blocked IPs, and the audit log (Req 29.2).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AdminPanel status={status} error={error}>
          <div className="grid gap-6 lg:grid-cols-3">
            <div>
              <p className="mb-2 flex items-center gap-1 text-sm font-medium text-foreground">
                <ListChecks size={16} /> Login attempts
              </p>
              {loginAttempts.length === 0 ? (
                <p className="text-sm text-muted-foreground">None recorded.</p>
              ) : (
                <ul className="space-y-1">
                  {loginAttempts.map((a) => (
                    <li
                      key={a.id}
                      className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-1.5 text-xs"
                    >
                      <span className="truncate text-foreground">
                        {a.email || a.ip || "unknown"}
                      </span>
                      <Badge variant={a.success ? "success" : "warning"}>
                        {a.success ? "ok" : "fail"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="mb-2 flex items-center gap-1 text-sm font-medium text-foreground">
                <Prohibit size={16} /> Blocked IPs
              </p>
              {blockedIps.length === 0 ? (
                <p className="text-sm text-muted-foreground">None blocked.</p>
              ) : (
                <ul className="space-y-1">
                  {blockedIps.map((b) => (
                    <li
                      key={b.id}
                      className="rounded-md border border-border bg-card px-3 py-1.5 text-xs"
                    >
                      <p className="font-mono text-foreground">{b.ip}</p>
                      <p className="text-muted-foreground">
                        {b.reason || "blocked"}
                        {b.blocked_until ? ` · until ${formatDate(b.blocked_until)}` : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="mb-2 flex items-center gap-1 text-sm font-medium text-foreground">
                <ListChecks size={16} /> Audit log
              </p>
              {auditLog.length === 0 ? (
                <p className="text-sm text-muted-foreground">No audit entries.</p>
              ) : (
                <ul className="space-y-1">
                  {auditLog.map((entry) => (
                    <li
                      key={entry.id}
                      className="rounded-md border border-border bg-card px-3 py-1.5 text-xs"
                    >
                      <p className="text-foreground">{entry.action}</p>
                      <p className="text-muted-foreground">
                        {formatDate(entry.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

function SettingsSection() {
  const { data, status, error, setData } = useAdminData(getSettings);
  const settings = data?.settings ?? {};

  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const onApply = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      // Try to parse the value as JSON (number/bool/object); fall back to string.
      let parsed = value;
      try {
        parsed = JSON.parse(value);
      } catch {
        /* keep raw string */
      }
      const updated = await updateSettings({ [key.trim()]: parsed });
      setData(updated);
      toast.success("Settings applied platform-wide");
      setKey("");
      setValue("");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Gear size={20} className="text-primary" />
          Platform settings
        </CardTitle>
        <CardDescription>
          Apply settings platform-wide immediately (Req 29.4).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={onApply}>
          <div className="space-y-1.5">
            <Label htmlFor="setting-key">Key</Label>
            <Input
              id="setting-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="jwt_expiry"
              required
            />
          </div>
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="setting-value">Value</Label>
            <Input
              id="setting-value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder='3600 or "value" or {"a":1}'
              required
            />
          </div>
          <Button type="submit" disabled={busy || !key.trim() || value === ""}>
            <Plus size={16} /> Apply
          </Button>
        </form>

        <AdminPanel status={status} error={error}>
          {Object.keys(settings).length === 0 ? (
            <p className="text-sm text-muted-foreground">No settings configured.</p>
          ) : (
            <ul className="space-y-1">
              {Object.entries(settings).map(([k, v]) => (
                <li
                  key={k}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-4 py-2"
                >
                  <span className="font-mono text-sm text-foreground">{k}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

export default function SecurityPanel() {
  return (
    <section className="space-y-6">
      <SecuritySection />
      <SettingsSection />
    </section>
  );
}
