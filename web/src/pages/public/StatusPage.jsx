import { useEffect, useState } from "react";
import { CircleNotch, CheckCircle, WarningCircle, MinusCircle } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { MarketingShell, MarketingPageHeader } from "@/components/public/PublicPage";
import { marketingImages } from "@/lib/marketingImages";
import { getServiceStatus } from "@/lib/publicApi";

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
  const [state, setState] = useState("loading");

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
    <MarketingShell
      eyebrow="Platform"
      title="Service status"
      subtitle="Live operational status of IoTAPS platform services."
      image={marketingImages.heroFleet}
      imageAlt="Platform infrastructure monitoring"
    >
      <MarketingPageHeader title="Current health" subtitle="Polled from the public health endpoint." />

      {state === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : state === "error" ? (
        <article className="blynk-platform-card p-6">
          <div className="flex items-center gap-2">
            <WarningCircle size={22} className="text-amber-500" />
            <h3 className="text-lg font-bold">Status unavailable</h3>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            We couldn&apos;t reach the status service right now. Please try again shortly.
          </p>
        </article>
      ) : (
        <div className="space-y-6">
          <article className="blynk-platform-card p-6 sm:p-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                {OverallIcon ? <OverallIcon size={24} className={overall.tone} weight="fill" /> : null}
                <h3 className="text-lg font-bold">
                  {health.status === "ok" ? "All systems operational" : "Some systems degraded"}
                </h3>
              </div>
              <Badge variant={overall.variant}>{overall.label}</Badge>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{health.service}</p>
          </article>

          <div className="space-y-3">
            <h2 className="text-sm font-bold uppercase tracking-wide text-foreground">Dependencies</h2>
            {health.dependencies?.length ? (
              health.dependencies.map((dep) => {
                const meta = statusMeta(dep.status);
                const Icon = meta.icon;
                return (
                  <article
                    key={dep.name}
                    className="blynk-platform-card flex items-center justify-between gap-4 px-6 py-4"
                  >
                    <div className="flex items-center gap-2">
                      <Icon size={20} className={meta.tone} weight="fill" />
                      <span className="text-sm font-medium text-foreground">{prettyName(dep.name)}</span>
                    </div>
                    <Badge variant={meta.variant}>{meta.label}</Badge>
                  </article>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">No dependencies reported.</p>
            )}
          </div>
        </div>
      )}
    </MarketingShell>
  );
}
