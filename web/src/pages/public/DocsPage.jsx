import { PublicPage, PageHeader } from "@/components/public/PublicPage";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";

// Public Docs / API page (Task 21.1, Req 31.1). A concise developer-facing
// overview of the REST API surface and MQTT topic structure. Endpoint shapes
// mirror the API in app/api/v1 and the design document.

const endpointGroups = [
  {
    title: "Authentication",
    endpoints: [
      { method: "POST", path: "/api/v1/auth/register" },
      { method: "POST", path: "/api/v1/auth/login" },
      { method: "POST", path: "/api/v1/auth/refresh" },
      { method: "POST", path: "/api/v1/auth/logout" },
    ],
  },
  {
    title: "Devices & telemetry",
    endpoints: [
      { method: "GET", path: "/api/v1/devices" },
      { method: "POST", path: "/api/v1/devices" },
      { method: "GET", path: "/api/v1/devices/{id}/telemetry" },
      { method: "POST", path: "/api/v1/devices/{id}/commands" },
    ],
  },
  {
    title: "Dashboards & rules",
    endpoints: [
      { method: "GET", path: "/api/v1/dashboards" },
      { method: "POST", path: "/api/v1/dashboards/{id}/share" },
      { method: "GET", path: "/api/v1/rules" },
      { method: "POST", path: "/api/v1/rules/from-template" },
    ],
  },
  {
    title: "Billing & status",
    endpoints: [
      { method: "GET", path: "/api/v1/billing/plans" },
      { method: "POST", path: "/api/v1/billing/quote" },
      { method: "GET", path: "/api/v1/changelog" },
      { method: "GET", path: "/api/v1/health" },
    ],
  },
];

const methodColor = {
  GET: "text-emerald-600 dark:text-emerald-400",
  POST: "text-sky-600 dark:text-sky-400",
  PATCH: "text-amber-600 dark:text-amber-400",
  DELETE: "text-rose-600 dark:text-rose-400",
};

export default function DocsPage() {
  return (
    <PublicPage className="max-w-5xl">
      <PageHeader
        title="Docs / API"
        subtitle="The IoTAPS REST API is versioned under /api/v1 and authenticated with a bearer JWT."
      />

      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="text-lg">Getting started</CardTitle>
          <CardDescription>
            Authenticate to receive a JWT access token and a refresh token, then
            send the access token as an{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">Authorization: Bearer</code>{" "}
            header on subsequent requests.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-sm font-medium text-foreground">MQTT topics</p>
          <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs text-foreground">
{`iotaps/{org_id}/{device_id}/telemetry   # device -> broker
iotaps/{org_id}/{device_id}/command     # broker -> device
iotaps/{org_id}/{device_id}/ack         # device -> broker
iotaps/{org_id}/{device_id}/status      # device -> broker (LWT)`}
          </pre>
        </CardContent>
      </Card>

      <div className="grid gap-6 sm:grid-cols-2">
        {endpointGroups.map((group) => (
          <Card key={group.title}>
            <CardHeader>
              <CardTitle className="text-base">{group.title}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 font-mono text-xs">
                {group.endpoints.map((ep) => (
                  <li key={`${ep.method} ${ep.path}`} className="flex gap-3">
                    <span className={`w-12 shrink-0 font-semibold ${methodColor[ep.method] || ""}`}>
                      {ep.method}
                    </span>
                    <span className="text-muted-foreground">{ep.path}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>
    </PublicPage>
  );
}
