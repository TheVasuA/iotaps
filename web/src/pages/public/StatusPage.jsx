import { useEffect, useState } from "react";
import { CircleNotch, CheckCircle, WarningCircle, MinusCircle } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PublicPage, PageHeader } from "@/components/public/PublicPage";
import { getServiceStatus } from "@/lib/publicApi";

// Public Status page (Task 21.1, Req 31.4). Displays the current operational
// status of platform services by polling the public GET /health endpoint, which
// reports overall API health plus per-dependency status.

// Map a dependency/overall status string to display metadata.
const STATUS_META = {
  ok: { label: "Operational", variant: "success", icon: CheckCircle, tone: "text-emerald-500" },
  degraded: { label: "Degraded", variant: "warning", icon: WarningCircle, tone: "text-amber-500" },
  unconfigured: { label: "Not configured", variant: "muted", icon: MinusCircle, tone: "text-muted-foreground" },
};

function statusMeta(status) {
  return STATUS_META[status] || { label: status, variant: "muted", icon: MinusCircle, tone: "text-muted-foreground" };
}

function prettyName(name) {
  if (!name) return "Service";
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export default function StatusPage() {
  const [health, setHealth] = useState(null);
  const [state, setState] = useState("loading"); // loading | ready | error

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getServiceStatus();
        if (!cancelled) {
          setHealth(data);
          setState("ready");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const overall = health ? statusMeta(health.status) : null;
  const OverallIcon = overall?.icon;

  return (
    <PublicPage>
      <PageHeader
        title="Service status"
        subtitle="Live operational status of IoTAPS platform services."
      />

      {state === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : state === "error" ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <WarningCircle size={22} className="text-amber-500" />
              <CardTitle className="text-lg">Status unavailable</CardTitle>
            </div>
            <CardDescription>
              We couldn&apos;t reach the status service right now. Please try again
              shortly.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {OverallIcon ? <OverallIcon size={24} className={overall.tone} weight="fill" /> : null}
                  <CardTitle className="text-lg">
                    {health.status === "ok"
                      ? "All systems operational"
                      : "Some systems degraded"}
                  </CardTitle>
                </div>
                <Badge variant={overall.variant}>{overall.label}</Badge>
              </div>
              <CardDescription>{health.service}</CardDescription>
            </CardHeader>
          </Card>

          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-foreground">Dependencies</h2>
            {health.dependencies?.length ? (
              health.dependencies.map((dep) => {
                const meta = statusMeta(dep.status);
                const Icon = meta.icon;
                return (
                  <Card key={dep.name}>
                    <CardContent className="flex items-center justify-between gap-4 py-4">
                      <div className="flex items-center gap-2">
                        <Icon size={20} className={meta.tone} weight="fill" />
                        <span className="text-sm font-medium text-foreground">
                          {prettyName(dep.name)}
                        </span>
                      </div>
                      <Badge variant={meta.variant}>{meta.label}</Badge>
                    </CardContent>
                  </Card>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">
                No dependencies reported.
              </p>
            )}
          </div>
        </div>
      )}
    </PublicPage>
  );
}
