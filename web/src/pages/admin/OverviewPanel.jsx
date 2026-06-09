import {
  Buildings,
  HardDrives,
  UsersThree,
  WifiHigh,
  CurrencyInr,
} from "@phosphor-icons/react";
import { getOverview } from "@/lib/adminApi";
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

// Super_Admin overview panel (Task 20.7, Req 23.1). Surfaces platform-wide
// counts, online devices, revenue, and per-service health from GET
// /admin/overview.

function StatCard({ icon: Icon, label, value }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-6">
        <span className="flex h-12 w-12 items-center justify-center rounded-md bg-secondary text-primary">
          <Icon size={24} />
        </span>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold text-foreground">{value}</p>
        </div>
      </CardContent>
    </Card>
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
    <section className="space-y-6">
      <AdminPanel status={status} error={error}>
        {data ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <StatCard icon={Buildings} label="Companies" value={data.companies} />
              <StatCard icon={HardDrives} label="Devices" value={data.devices} />
              <StatCard icon={UsersThree} label="Users" value={data.users} />
              <StatCard icon={WifiHigh} label="Online now" value={data.online} />
              <StatCard
                icon={CurrencyInr}
                label="Revenue"
                value={`₹${data.revenue}`}
              />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Server health</CardTitle>
                <CardDescription>
                  Live status of platform infrastructure.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data.server_health &&
                Object.keys(data.server_health).length > 0 ? (
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {Object.entries(data.server_health).map(([key, val]) => (
                      <li
                        key={key}
                        className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-2"
                      >
                        <span className="text-sm capitalize text-foreground">
                          {key.replace(/_/g, " ")}
                        </span>
                        <Badge variant={healthVariant(String(val))}>
                          {String(val)}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No server health metrics reported.
                  </p>
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </AdminPanel>
    </section>
  );
}
