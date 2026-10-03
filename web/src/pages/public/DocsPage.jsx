import { Link } from "react-router-dom";
import { MarketingShell, MarketingPageHeader } from "@/components/public/PublicPage";
import { MarketingRelatedLinks } from "@/pages/public/marketing/createMarketingPage";
import { marketingImages } from "@/lib/marketingImages";

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
    <MarketingShell
      eyebrow="Developers"
      title="Docs / API"
      subtitle="The IoTAPS REST API is versioned under /api/v1 and authenticated with a bearer JWT."
      image={marketingImages.consoleDesk}
      imageAlt="Developer workspace with IoT dashboard"
      metaTitle="API & developer documentation"
      metaDescription="REST API reference for IoTAPS: JWT auth, devices, telemetry, commands, dashboards, rules, and billing under /api/v1 — plus MQTT topic conventions."
      wide
    >
      <MarketingRelatedLinks
        title="Developer guides"
        links={[
          { to: "/developers/mqtt-devices", label: "MQTT & devices" },
          { to: "/developers/dashboards-api", label: "Dashboards API" },
          { to: "/changelog", label: "Release notes" },
          { to: "/platform", label: "Platform overview" },
        ]}
      />
      <article className="blynk-platform-card mb-8 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide">Getting started</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          Authenticate to receive a JWT access token and a refresh token, then send the access token
          as an{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">Authorization: Bearer</code>{" "}
          header on subsequent requests.
        </p>
        <p className="mt-6 text-sm font-bold uppercase tracking-wide text-foreground">MQTT topics</p>
        <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-muted/50 p-4 text-xs leading-relaxed text-foreground">
          {`# Token form (recommended — what firmware uses)
iotaps/{token}/telemetry        # device -> broker
iotaps/{token}/command          # broker -> device
iotaps/{token}/ack              # device -> broker
iotaps/{token}/status           # device -> broker (LWT)

# Org/device form (alternative)
iotaps/{org_id}/{device_id}/{telemetry|command|ack|status}`}
        </pre>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          Full topic table, payload contracts, and sample clients on the{" "}
          <Link to="/developers/mqtt-devices" className="font-medium text-primary hover:underline">
            MQTT & devices
          </Link>{" "}
          page.
        </p>
      </article>

      <MarketingPageHeader title="Endpoint reference" subtitle="Representative routes — see OpenAPI in the API for full schemas." />

      <div className="grid gap-4 sm:grid-cols-2">
        {endpointGroups.map((group) => (
          <article key={group.title} className="blynk-platform-card p-6">
            <h3 className="text-base font-bold uppercase tracking-wide">{group.title}</h3>
            <ul className="mt-4 space-y-2.5 font-mono text-xs">
              {group.endpoints.map((ep) => (
                <li key={`${ep.method} ${ep.path}`} className="flex gap-3 border-b border-border/60 pb-2 last:border-0">
                  <span className={`w-12 shrink-0 font-bold ${methodColor[ep.method] || ""}`}>
                    {ep.method}
                  </span>
                  <span className="text-muted-foreground">{ep.path}</span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </MarketingShell>
  );
}
