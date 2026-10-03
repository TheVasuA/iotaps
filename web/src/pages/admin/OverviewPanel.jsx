import { Link } from "react-router-dom";
import {
  Buildings,
  HardDrives,
  UsersThree,
  WifiHigh,
  CurrencyInr,
  ArrowRight,
} from "@phosphor-icons/react";
import { getOverview } from "@/lib/adminApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import { ADMIN_HUB_SECTIONS } from "@/lib/adminNav";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="iotaps-admin-stat-card">
      <span className="iotaps-admin-stat-icon">
        <Icon size={22} weight="duotone" />
      </span>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold tabular-nums text-foreground">{value}</p>
      </div>
    </div>
  );
}

function healthVariant(status) {
  if (status === "ok") return "success";
  if (status === "degraded") return "warning";
  return "muted";
}

export default function OverviewPanel() {
  const { data, status, error } = useAdminData(getOverview);

  return (
    <div className="space-y-8">
      <header className="iotaps-admin-hero">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary">Super admin</p>
        <h1 className="mt-2 font-brand text-2xl font-bold tracking-tight sm:text-3xl">
          Platform control center
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Manage organizations, users, devices, MQTT infrastructure, billing, content, and security
          from one place — aligned with what tenants see in the console.
        </p>
      </header>

      <AdminPanel status={status} error={error}>
        {data ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard icon={Buildings} label="Organizations" value={data.companies} />
              <StatCard icon={HardDrives} label="Devices" value={data.devices} />
              <StatCard icon={UsersThree} label="Users" value={data.users} />
              <StatCard icon={WifiHigh} label="Online now" value={data.online} />
              <StatCard icon={CurrencyInr} label="Revenue (₹)" value={data.revenue} />
            </div>

            {data.server_health && Object.keys(data.server_health).length > 0 ? (
              <section className="mt-6 rounded-xl border border-border bg-card p-5">
                <h2 className="text-sm font-bold uppercase tracking-wide text-foreground">
                  Infrastructure health
                </h2>
                <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(data.server_health).map(([key, val]) => (
                    <li
                      key={key}
                      className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2"
                    >
                      <span className="text-sm capitalize text-foreground">
                        {key.replace(/_/g, " ")}
                      </span>
                      <Badge variant={healthVariant(String(val))}>{String(val)}</Badge>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        ) : null}
      </AdminPanel>

      <section aria-labelledby="admin-hub-heading">
        <h2 id="admin-hub-heading" className="text-lg font-bold tracking-tight">
          Manage everything
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Jump to the tool that matches each part of the IoTAPS product.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {ADMIN_HUB_SECTIONS.map((section) => (
            <Link
              key={section.title}
              to={section.to}
              className={cn(
                "group flex flex-col rounded-xl border border-border bg-card p-5 transition",
                "hover:border-primary/35 hover:shadow-md"
              )}
            >
              <h3 className="text-sm font-bold text-foreground group-hover:text-primary">{section.title}</h3>
              <p className="mt-2 flex-1 text-xs leading-relaxed text-muted-foreground">{section.description}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-primary">
                {section.cta}
                <ArrowRight size={14} weight="bold" />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
