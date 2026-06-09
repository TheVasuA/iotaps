import { getRevenue } from "@/lib/adminApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";

// Super_Admin revenue analytics panel (Task 20.7, Req 25.1). Surfaces MRR, ARR,
// churn, ARPU, the conversion funnel, revenue by source, and the top
// organizations from GET /admin/revenue.

function Metric({ label, value }) {
  return (
    <Card>
      <CardContent className="p-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}

function money(value) {
  return `₹${Number(value ?? 0).toLocaleString()}`;
}

function percent(value) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}

export default function RevenuePanel() {
  const { data, status, error } = useAdminData(getRevenue);

  return (
    <section className="space-y-6">
      <AdminPanel status={status} error={error}>
        {data ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="MRR" value={money(data.mrr)} />
              <Metric label="ARR" value={money(data.arr)} />
              <Metric label="Churn" value={percent(data.churn)} />
              <Metric label="ARPU" value={money(data.arpu)} />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Conversion funnel</CardTitle>
                  <CardDescription>
                    Organizations through to paying customers.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {data.funnel ? (
                    <ul className="space-y-2 text-sm">
                      <li className="flex justify-between">
                        <span className="text-muted-foreground">Organizations</span>
                        <span className="font-medium text-foreground">
                          {data.funnel.organizations}
                        </span>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-muted-foreground">
                          With subscription
                        </span>
                        <span className="font-medium text-foreground">
                          {data.funnel.with_subscription}
                        </span>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-muted-foreground">Paying</span>
                        <span className="font-medium text-foreground">
                          {data.funnel.paying}
                        </span>
                      </li>
                      <li className="flex justify-between border-t border-border pt-2">
                        <span className="text-muted-foreground">
                          Conversion rate
                        </span>
                        <span className="font-medium text-foreground">
                          {percent(data.funnel.conversion_rate)}
                        </span>
                      </li>
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">No funnel data.</p>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Revenue by source</CardTitle>
                  <CardDescription>Where revenue originates.</CardDescription>
                </CardHeader>
                <CardContent>
                  {data.by_source && Object.keys(data.by_source).length > 0 ? (
                    <ul className="space-y-2 text-sm">
                      {Object.entries(data.by_source).map(([src, amount]) => (
                        <li key={src} className="flex justify-between">
                          <span className="capitalize text-muted-foreground">
                            {src.replace(/_/g, " ")}
                          </span>
                          <span className="font-medium text-foreground">
                            {money(amount)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No revenue by source.
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Top organizations</CardTitle>
                <CardDescription>By total revenue.</CardDescription>
              </CardHeader>
              <CardContent>
                {data.top_orgs && data.top_orgs.length > 0 ? (
                  <ul className="space-y-2">
                    {data.top_orgs.map((org) => (
                      <li
                        key={org.org_id}
                        className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-2"
                      >
                        <span className="text-sm text-foreground">{org.name}</span>
                        <span className="text-sm font-medium text-foreground">
                          {money(org.revenue)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No organizations with revenue yet.
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
