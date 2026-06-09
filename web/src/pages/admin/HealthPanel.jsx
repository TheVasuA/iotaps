import { getHealth, getErrors } from "@/lib/adminApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Heartbeat, WarningCircle } from "@phosphor-icons/react";

// Super_Admin health & errors panel (Task 20.7, Req 28.1, 28.3). Surfaces
// per-service health (GET /admin/health) and recent errors + trends
// (GET /admin/errors).

function serviceVariant(status) {
  if (status === "ok") return "success";
  if (status === "degraded") return "warning";
  return "muted";
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function HealthSection() {
  const { data, status, error } = useAdminData(getHealth);
  const services = data?.services ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Heartbeat size={20} className="text-primary" />
          Service health
        </CardTitle>
        <CardDescription>Status of each platform service (Req 28.1).</CardDescription>
      </CardHeader>
      <CardContent>
        <AdminPanel status={status} error={error}>
          {services.length === 0 ? (
            <p className="text-sm text-muted-foreground">No services reported.</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {services.map((svc) => (
                <li
                  key={svc.name}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-2"
                >
                  <span className="text-sm capitalize text-foreground">
                    {svc.name.replace(/_/g, " ")}
                  </span>
                  <Badge variant={serviceVariant(svc.status)}>{svc.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

function ErrorsSection() {
  const { data, status, error } = useAdminData(() => getErrors());
  const recent = data?.recent ?? [];
  const trends = data?.trends ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <WarningCircle size={20} className="text-primary" />
          Errors
        </CardTitle>
        <CardDescription>Recent errors and error trends (Req 28.3).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AdminPanel status={status} error={error}>
          <>
            {trends.length > 0 ? (
              <div>
                <p className="mb-2 text-sm font-medium text-foreground">
                  Trend (last {trends.length} days)
                </p>
                <div className="flex items-end gap-1">
                  {trends.map((t) => {
                    const max = Math.max(...trends.map((x) => x.count), 1);
                    const height = Math.max(4, (t.count / max) * 64);
                    return (
                      <div
                        key={t.date}
                        className="flex-1 rounded-sm bg-primary/70"
                        style={{ height: `${height}px` }}
                        title={`${t.date}: ${t.count}`}
                      />
                    );
                  })}
                </div>
              </div>
            ) : null}

            <div>
              <p className="mb-2 text-sm font-medium text-foreground">Recent</p>
              {recent.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recent errors.</p>
              ) : (
                <ul className="space-y-2">
                  {recent.map((e) => (
                    <li
                      key={e.id}
                      className="rounded-md border border-border bg-card px-4 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {e.error_code || "error"}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {formatDate(e.created_at)}
                        </span>
                      </div>
                      <p className="text-sm text-foreground">{e.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

export default function HealthPanel() {
  return (
    <section className="space-y-6">
      <HealthSection />
      <ErrorsSection />
    </section>
  );
}
