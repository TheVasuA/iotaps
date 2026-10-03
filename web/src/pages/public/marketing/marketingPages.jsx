import { Link } from "react-router-dom";
import { marketingImages } from "@/lib/marketingImages";
import {
  createMarketingPage,
  MarketingCardGrid,
  MarketingBlogList,
  MarketingCtaInline,
  MarketingRelatedLinks,
} from "./createMarketingPage";
import { MarketingShell } from "@/components/public/PublicPage";
import { MarketingImage } from "@/components/public/MarketingSubpage";

const solutionRelated = [
  { to: "/solutions/industrial-iot", label: "Industrial IoT" },
  { to: "/solutions/smart-agriculture", label: "Smart agriculture" },
  { to: "/solutions/energy-hvac", label: "Energy & HVAC" },
  { to: "/enterprise", label: "Enterprise" },
];

const developerRelated = [
  { to: "/docs", label: "Documentation" },
  { to: "/developers/mqtt-devices", label: "MQTT & devices" },
  { to: "/developers/dashboards-api", label: "Dashboards API" },
  { to: "/changelog", label: "Release notes" },
];

export const PlatformOverviewPage = createMarketingPage({
  shell: {
    eyebrow: "Platform",
    title: "IoTAPS platform overview",
    subtitle:
      "One multi-tenant stack for device provisioning, live telemetry, dashboards, automations, and billing — built for teams shipping connected products.",
    image: marketingImages.heroConsolePreview,
    imageAlt: "IoT platform dashboard preview",
    metaTitle: "IoT platform — provisioning, telemetry, dashboards & billing",
    metaDescription:
      "Multi-tenant IoT platform: MQTT device provisioning, WebSocket telemetry, drag-and-drop dashboards, visual rule chains, and subscription billing in one stack.",
  },
  relatedLinks: [
    { to: "/pricing", label: "Pricing" },
    { to: "/status", label: "System status" },
    { to: "/register", label: "Sign up free" },
  ],
  sections: [
    {
      heading: "Console & fleet",
      body: [
        "Provision devices with MQTT credentials, organize fleets in groups, and monitor online status from a branded web console.",
        "Role-based access separates platform admins, project centers, and device users with theme-aware UI.",
      ],
    },
    {
      heading: "Data & automation",
      body: [
        "WebSocket telemetry streams to dashboard widgets as it arrives. Visual rule chains connect triggers, conditions, and actions without redeploying firmware.",
        "MQTT explorer and RPC commands help debug integrations in production.",
      ],
    },
    {
      heading: "Commercial layer",
      body: [
        "Free and Pro plans with volume pricing, Razorpay checkout, referrals, and partner wallet commissions — so you can grow fleets without replatforming.",
      ],
    },
  ],
});

export const IndustrialIotPage = createMarketingPage({
  shell: {
    eyebrow: "Solutions",
    title: "Industrial IoT",
    subtitle:
      "Monitor lines, assets, and environmental sensors across plants with unified dashboards, alerts, and tenant isolation.",
    image: marketingImages.industrialPlant,
    imageAlt: "Industrial automation and connected manufacturing",
  },
  relatedLinks: solutionRelated,
  sections: [
    {
      heading: "Use cases",
      body: [
        "Predictive maintenance from vibration and temperature telemetry, OEE dashboards for supervisors, and secure per-site device groups for integrators.",
      ],
    },
    {
      heading: "How IoTAPS helps",
      body: [
        "QR provisioning for field installs, maintenance mode for safe downtime, and rule chains that notify Slack, email, or webhooks when thresholds breach.",
      ],
    },
  ],
});

export const SmartAgriculturePage = createMarketingPage({
  shell: {
    eyebrow: "Solutions",
    title: "Smart agriculture",
    subtitle:
      "Greenhouse, irrigation, and soil monitoring with mobile-friendly dashboards for agronomists and operators.",
    image: marketingImages.solutionsAgriculture,
    imageAlt: "Smart agriculture IoT sensors in the field",
  },
  relatedLinks: solutionRelated,
  sections: [
    {
      heading: "Field to cloud",
      body: [
        "Connect LoRa, cellular, or Wi-Fi gateways over MQTT, map telemetry to widgets, and share read-only dashboard links with growers.",
      ],
    },
    {
      heading: "Automation",
      body: [
        "Schedule irrigation rules from soil moisture readings, log historical series for compliance, and scale tenants per farm or cooperative.",
      ],
    },
  ],
});

export const EnergyHvacPage = createMarketingPage({
  shell: {
    eyebrow: "Solutions",
    title: "Energy & HVAC",
    subtitle:
      "Track consumption, solar generation, and HVAC performance across buildings and utility portfolios.",
    image: marketingImages.energyGrid,
    imageAlt: "Energy and solar monitoring",
  },
  relatedLinks: solutionRelated,
  sections: [
    {
      heading: "Building operations",
      body: [
        "Aggregate meter data, set demand alerts, and give facility managers live gauges without custom SCADA projects.",
      ],
    },
    {
      heading: "Integrations",
      body: [
        "Push telemetry to partner systems via HTTP rule nodes, export API data for billing, and retain history per plan tier.",
      ],
    },
  ],
});

export const EnterprisePage = createMarketingPage({
  shell: {
    eyebrow: "Enterprise",
    title: "Enterprise & regulated deployments",
    subtitle:
      "Multi-tenant org structure, role-based access, and self-hosted deployment options for large fleets and OEM programs.",
    image: marketingImages.heroFleet,
    imageAlt: "Enterprise fleet operations center",
    metaTitle: "Enterprise IoT deployments & OEM programs",
    metaDescription:
      "Multi-tenant org structure, role-based console access, TOTP 2FA, per-org MQTT isolation, retention tiers, and self-hosted Docker/Kubernetes deployment for large IoT fleets.",
  },
  relatedLinks: [
    { to: "/contact", label: "Contact sales" },
    { to: "/security", label: "Security" },
    { to: "/platform", label: "Platform overview" },
  ],
  sections: [
    {
      heading: "Org structure & access",
      body: [
        "Organizations are the tenant boundary: devices, dashboards, rules, members, and billing all live under one org, and members are invited into the org with a chosen role.",
        "Three console roles separate duties — super admin, project center, and device user — so fleet management can be delegated without handing out platform-wide control.",
        "Volume pricing scales with fleet size; POST /billing/quote returns the unit price and total for a device count and billing cycle.",
      ],
    },
    {
      heading: "Security",
      body: [
        "Console accounts support TOTP two-factor authentication with one-time backup codes, and API access uses JWT bearer tokens scoped to the caller's tenant.",
        "MQTT credentials are isolated per organization: each org's broker credentials are ACL-restricted to iotaps/{org_id}/# so one tenant cannot publish or subscribe under another's topics. Production deployments terminate TLS for API and MQTT traffic.",
      ],
    },
    {
      heading: "Data lifecycle",
      body: [
        "Telemetry is stored in TimescaleDB with plan-defined retention tiers: raw readings expire on the plan's retention window while downsampled hourly aggregates are kept longer for trend views.",
        "Background workers enforce retention and rebuild the downsampling aggregates, and history can be pulled out via per-device CSV export or generated CSV/PDF reports.",
      ],
    },
    {
      heading: "Deployment options",
      body: [
        "Run on the hosted SaaS, or self-host using the Docker Compose and Kubernetes/Kustomize manifests in the repository, with documented off-site backup/restore procedures and an optional MongoDB identity vault for credential escrow.",
        "In-console support chat connects device users with their project center. For anything that needs a person, the contact form at /contact reaches the IoTAPS team.",
      ],
    },
  ],
  children: () => <MarketingCtaInline title="Plan a deployment" to="/contact" label="Contact sales" />,
});

function MqttTopicTable({ rows }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted-foreground">
            <th className="py-2 pr-4 font-bold">Topic</th>
            <th className="py-2 pr-4 font-bold">Direction</th>
            <th className="py-2 font-bold">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.topic} className="border-b border-border/60 last:border-0">
              <td className="py-2 pr-4 font-mono text-foreground">{row.topic}</td>
              <td className="py-2 pr-4 whitespace-nowrap text-muted-foreground">{row.direction}</td>
              <td className="py-2 text-muted-foreground">{row.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MqttCodeBlock({ label, code }) {
  return (
    <div className="mt-6">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
      <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-muted/50 p-4 text-xs leading-relaxed text-foreground">
        {code}
      </pre>
    </div>
  );
}

/**
 * `/developers/mqtt-devices` — reference docs for the MQTT contract the
 * backend validators and the ESP32 firmware in `firmware/` actually implement:
 * token topics `iotaps/{token}/{type}` plus the legacy org/device form.
 */
export function MqttDevicesPage() {
  return (
    <MarketingShell
      eyebrow="Developers"
      title="MQTT & devices"
      subtitle="Topic reference, payload contracts, and sample clients for firmware and gateway teams."
      image={marketingImages.fleetLogistics}
      imageAlt="Connected devices and logistics telemetry"
      metaTitle="MQTT topic & payload reference"
      metaDescription="IoTAPS MQTT reference: token and org/device topic forms, telemetry/command/ack/status payload contracts, per-org ACLs, and Arduino, Python, and JavaScript samples."
      wide
    >
      <MarketingRelatedLinks links={developerRelated} />

      <article className="blynk-platform-card mb-8 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide">Topic layout</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          Every message lives under the{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">iotaps</code> root. The
          final segment is the message type —{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">telemetry</code>,{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">command</code>,{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">ack</code>, or{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">status</code>. Two
          addressing forms are accepted; the token form is what current firmware uses.
        </p>

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">Token form (recommended)</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Three segments — the device token issued by the console stands in for org and device IDs.
        </p>
        <MqttTopicTable
          rows={[
            {
              topic: "iotaps/{token}/telemetry",
              direction: "device → broker",
              notes: "JSON readings. Only this type counts toward the Free-plan message quota.",
            },
            {
              topic: "iotaps/{token}/command",
              direction: "broker → device",
              notes: "Subscribe at connect time to receive commands.",
            },
            {
              topic: "iotaps/{token}/ack",
              direction: "device → broker",
              notes: "Command acknowledgement, correlated by command_id.",
            },
            {
              topic: "iotaps/{token}/status",
              direction: "device → broker",
              notes: "online/offline presence; use as the last-will (LWT) topic.",
            },
          ]}
        />

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">Org/device form (alternative)</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Four segments — the same four types addressed by org and device IDs.
        </p>
        <MqttTopicTable
          rows={[
            {
              topic: "iotaps/{org_id}/{device_id}/telemetry",
              direction: "device → broker",
              notes: "Same payload contract as the token form.",
            },
            {
              topic: "iotaps/{org_id}/{device_id}/command",
              direction: "broker → device",
              notes: "Same payload contract as the token form.",
            },
            {
              topic: "iotaps/{org_id}/{device_id}/ack",
              direction: "device → broker",
              notes: "Same payload contract as the token form.",
            },
            {
              topic: "iotaps/{org_id}/{device_id}/status",
              direction: "device → broker",
              notes: "Same payload contract as the token form.",
            },
          ]}
        />

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">ACLs & wildcards</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Per-organization broker credentials are restricted to{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">iotaps/{"{org_id}"}/#</code>{" "}
          and cannot reach another org's topics. In topic filters,{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">+</code> matches exactly
          one level and <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">#</code>{" "}
          matches the remaining levels (final segment only). The platform's own listener connects with
          privileged internal credentials and subscribes across orgs.
        </p>
      </article>

      <article className="blynk-platform-card mb-8 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide">Payload contracts</h2>

        <h3 className="mt-5 text-sm font-bold uppercase tracking-wide">Telemetry</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Two shapes are accepted: a strict envelope with an ISO-8601 timestamp, or a flat object of
          numeric readings (the server stamps the time). Keys{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">ts</code> and{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">data</code> are reserved
          for the envelope; all values must be JSON numbers.
        </p>
        <MqttCodeBlock
          label="Strict envelope"
          code={`{"ts": "2026-10-02T12:00:00Z", "data": {"temperature": 21.5, "humidity": 48.0}}`}
        />
        <MqttCodeBlock label="Simple readings" code={`{"temperature": 21.5, "humidity": 48.0}`} />

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">Command</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Published by the platform to{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">…/command</code>.{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">type</code> is{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">on</code>,{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">off</code>, or{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">value</code>;{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">target</code> names the
          metric/actuator, and <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">value</code>{" "}
          carries the number for <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">value</code>{" "}
          commands.
        </p>
        <MqttCodeBlock
          label="Command"
          code={`{"command_id": "…", "type": "value", "target": "brightness", "value": 128}`}
        />

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">Ack</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          The device replies on <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">…/ack</code>{" "}
          with a JSON object carrying the{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">command_id</code>; any
          extra fields (such as execution status) are forwarded to the console.
        </p>
        <MqttCodeBlock
          label="Ack"
          code={`{"command_id": "…", "status": "executed", "target": "brightness", "value": 128}`}
        />

        <h3 className="mt-6 text-sm font-bold uppercase tracking-wide">Status / LWT</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Publish <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">{"{\"status\":\"online\"}"}</code>{" "}
          retained on connect, and register the same topic as the last-will with{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">{"{\"status\":\"offline\"}"}</code>{" "}
          so the broker marks the device offline when the connection drops.
        </p>
        <MqttCodeBlock label="Status" code={`{"status": "online"}`} />
      </article>

      <article className="blynk-platform-card mb-8 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide">Sample clients</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          Short clients for the token form. The device token is used as the MQTT username and password
          (and typically as the client ID) — there are no separate broker credentials to provision.
        </p>

        <MqttCodeBlock
          label="Arduino / ESP32 (PubSubClient + ArduinoJson)"
          code={`#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* TOKEN = "dT_xxxxxxxx";        // device token from the console
const char* MQTT_HOST = "mqtt.iotaps.com";
const int   MQTT_PORT = 1883;

WiFiClient net;
PubSubClient mqtt(net);
String tTelemetry, tCommand, tAck, tStatus;

void onCommand(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, len)) return;
  const char* type   = doc["type"]   | "";   // "on" | "off" | "value"
  const char* target = doc["target"] | "";   // metric name, e.g. "led1"
  float value        = doc["value"]  | 0;
  // ...drive your actuators from type/target/value here...

  StaticJsonDocument<128> ack;
  ack["command_id"] = doc["command_id"] | "";
  ack["status"] = "executed";
  char buf[128];
  serializeJson(ack, buf);
  mqtt.publish(tAck.c_str(), buf);           // iotaps/{token}/ack
}

void connectMqtt() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  // LWT: the broker publishes offline for us if the connection drops
  mqtt.connect(TOKEN, TOKEN, TOKEN, tStatus.c_str(), 1, true, "{\\"status\\":\\"offline\\"}");
  mqtt.subscribe(tCommand.c_str());          // iotaps/{token}/command
  mqtt.publish(tStatus.c_str(), "{\\"status\\":\\"online\\"}", true);
}

void sendTelemetry() {
  StaticJsonDocument<192> doc;
  doc["temperature"] = 21.5;                 // numbers only
  doc["humidity"] = 48.0;
  char buf[192];
  serializeJson(doc, buf);
  mqtt.publish(tTelemetry.c_str(), buf);     // iotaps/{token}/telemetry
}

void setup() {
  // token form: iotaps/{token}/{type}
  tTelemetry = String("iotaps/") + TOKEN + "/telemetry";
  tCommand   = String("iotaps/") + TOKEN + "/command";
  tAck       = String("iotaps/") + TOKEN + "/ack";
  tStatus    = String("iotaps/") + TOKEN + "/status";
  WiFi.begin("ssid", "password");
  while (WiFi.status() != WL_CONNECTED) delay(500);
  connectMqtt();
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
  static unsigned long last = 0;
  if (millis() - last >= 5000) { last = millis(); sendTelemetry(); }
}`}
        />

        <MqttCodeBlock
          label="Python (paho-mqtt)"
          code={`import json, time
import paho.mqtt.client as mqtt

TOKEN = "dT_xxxxxxxx"                      # device token from the console
base = f"iotaps/{TOKEN}"                   # token form: iotaps/{token}/{type}

client = mqtt.Client(client_id=TOKEN)
client.username_pw_set(TOKEN, TOKEN)       # token is username and password
client.will_set(f"{base}/status", json.dumps({"status": "offline"}), qos=1, retain=True)
client.connect("mqtt.iotaps.com", 1883, keepalive=60)

client.subscribe(f"{base}/command")
client.publish(f"{base}/status", json.dumps({"status": "online"}), qos=1, retain=True)

while True:
    client.publish(
        f"{base}/telemetry",
        json.dumps({"temperature": 21.5, "humidity": 48.0}),
    )
    time.sleep(5)`}
        />

        <MqttCodeBlock
          label="JavaScript (MQTT.js)"
          code={`import mqtt from "mqtt";

const TOKEN = "dT_xxxxxxxx";               // device token from the console
const base = \`iotaps/\${TOKEN}\`;              // token form: iotaps/{token}/{type}

const client = mqtt.connect("mqtt://mqtt.iotaps.com:1883", {
  clientId: TOKEN,
  username: TOKEN,                         // token is username and password
  password: TOKEN,
  will: {
    topic: \`\${base}/status\`,
    payload: JSON.stringify({ status: "offline" }),
    qos: 1,
    retain: true,
  },
});

client.on("connect", () => {
  client.subscribe(\`\${base}/command\`);
  client.publish(\`\${base}/status\`, JSON.stringify({ status: "online" }), { qos: 1, retain: true });
  setInterval(() => {
    client.publish(\`\${base}/telemetry\`, JSON.stringify({ temperature: 21.5, humidity: 48.0 }));
  }, 5000);
});

client.on("message", (topic, payload) => {
  const msg = JSON.parse(payload.toString());
  if (topic === \`\${base}/command\`) {
    // msg = { command_id, type: "on"|"off"|"value", target, value? }
    client.publish(
      \`\${base}/ack\`,
      JSON.stringify({ command_id: msg.command_id, status: "executed" }),
    );
  }
});`}
        />
      </article>

      <article className="blynk-platform-card p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide">Provisioning & quota</h2>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          Create devices via the REST API or the console wizard to receive a device token; QR codes
          cover field pairing and groups cover bulk fleets. The token is the MQTT username and
          password shown above.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          On the Free plan, only telemetry messages count toward the message quota — commands, acks,
          and status/LWT messages are excluded.
        </p>
      </article>
    </MarketingShell>
  );
}

export const DashboardsApiPage = createMarketingPage({
  shell: {
    eyebrow: "Developers",
    title: "Dashboards API",
    subtitle: "Create dashboards, attach widgets, persist layouts, and share read-only links programmatically.",
    image: marketingImages.analyticsDashboard,
    imageAlt: "Analytics dashboards API",
  },
  relatedLinks: developerRelated,
  sections: [
    {
      heading: "Core endpoints",
      body: [
        "List and create dashboards with POST /api/v1/dashboards. PATCH layout JSON for widget positions. POST …/share for public URLs.",
        "Widgets bind to device telemetry keys consumed by the WebSocket stream in the console.",
      ],
    },
    {
      heading: "Next steps",
      body: [
        "Authenticate with JWT from /api/v1/auth/login, then explore the full endpoint reference on the main documentation page.",
      ],
    },
  ],
});

export const PartnersPage = createMarketingPage({
  shell: {
    eyebrow: "Company",
    title: "Partners & integrators",
    subtitle:
      "Refer customers, earn wallet commissions, and deliver IoT projects on a platform your clients can operate themselves.",
    image: marketingImages.consoleDesk,
    imageAlt: "Partner program and console",
  },
  relatedLinks: [
    { to: "/pricing", label: "Pricing" },
    { to: "/contact", label: "Become a partner" },
    { to: "/register", label: "Create account" },
  ],
  sections: [
    {
      heading: "Partner wallet",
      body: [
        "Track referral earnings and commissions inside the console. Share signup links and manage payouts as your deployed fleets grow.",
      ],
    },
    {
      heading: "System integrators",
      body: [
        "White-label friendly console surfaces, MQTT-native devices, and documentation your delivery teams can hand off to end customers.",
      ],
    },
  ],
});

export const SecurityContactPage = createMarketingPage({
  shell: {
    eyebrow: "Legal & trust",
    title: "Security contact",
    subtitle:
      "Report vulnerabilities, request security documentation, or reach our team for enterprise security reviews.",
    image: marketingImages.analyticsDashboard,
    imageAlt: "Security and compliance",
    showCta: false,
  },
  relatedLinks: [
    { to: "/privacy", label: "Privacy policy" },
    { to: "/terms", label: "Terms of service" },
  ],
  sections: [
    {
      heading: "Report an issue",
      body: [
        "Email security@iotaps.com with reproduction steps and impact. We acknowledge reports within two business days.",
        "For general support use support@iotaps.com or the contact form.",
      ],
    },
    {
      heading: "Practices",
      body: [
        "JWT authentication, optional TOTP 2FA, tenant-scoped API access, and encrypted transport for API and MQTT (TLS in production deployments).",
      ],
    },
  ],
});

/**
 * `/developers` index. The top nav and footer both point at the developer
 * surface, but only the two leaf pages existed — typing or linking `/developers`
 * fell through to the 404 catch-all. This is the hub those links expect.
 */
export const DevelopersHubPage = createMarketingPage({
  shell: {
    eyebrow: "Developers",
    title: "Developer platform",
    subtitle:
      "Everything needed to connect firmware, build dashboards, and automate fleets — MQTT topics, provisioning, and a versioned REST API.",
    image: marketingImages.analyticsDashboard,
    imageAlt: "IoT developer documentation and API reference",
    metaTitle: "Developer platform — MQTT, dashboards API & REST reference",
    metaDescription:
      "Connect firmware over MQTT, provision device credentials, and build dashboards programmatically with the versioned IoTAPS REST API under /api/v1.",
    wide: true,
  },
  relatedLinks: developerRelated,
  children: () => (
    <MarketingCardGrid
      items={[
        {
          eyebrow: "Devices",
          title: "MQTT & devices",
          body: "Per-device credentials, topic conventions, and provisioning flows for firmware and gateway teams.",
          to: "/developers/mqtt-devices",
        },
        {
          eyebrow: "API",
          title: "Dashboards API",
          body: "Create dashboards, attach widgets, persist layouts, and share read-only links programmatically.",
          to: "/developers/dashboards-api",
        },
        {
          eyebrow: "Reference",
          title: "REST API docs",
          body: "Versioned endpoints under /api/v1 for auth, devices, telemetry, rules, and billing.",
          to: "/docs",
        },
      ]}
    />
  ),
});

export function SolutionsHubPage() {
  return (
    <MarketingShell
      eyebrow="Solutions"
      title="Industry solutions"
      subtitle="Vertical playbooks on one platform — same console, rules engine, and billing for every deployment."
      image={marketingImages.industrialPlant}
      imageAlt="IoT solutions across industries"
      metaTitle="IoT solutions by industry"
      metaDescription="Industrial IoT, smart agriculture, and energy & HVAC playbooks on one platform — same console, rules engine, and billing for every deployment."
      wide
    >
      <MarketingCardGrid
        items={[
          {
            eyebrow: "Manufacturing",
            title: "Industrial IoT",
            body: "Asset monitoring, OEE views, and alerting for plants and OEM fleets.",
            to: "/solutions/industrial-iot",
          },
          {
            eyebrow: "Agritech",
            title: "Smart agriculture",
            body: "Soil, climate, and irrigation telemetry for greenhouses and cooperatives.",
            to: "/solutions/smart-agriculture",
          },
          {
            eyebrow: "Utilities",
            title: "Energy & HVAC",
            body: "Meters, solar, and building HVAC performance in one tenant workspace.",
            to: "/solutions/energy-hvac",
          },
          {
            eyebrow: "Scale",
            title: "Enterprise",
            body: "Security reviews, deployment options, and migration support.",
            to: "/enterprise",
          },
          {
            eyebrow: "Help",
            title: "FAQ",
            body: "Billing, devices, and getting started answers.",
            to: "/faq",
          },
          {
            eyebrow: "Patterns",
            title: "Deployment patterns",
            body: "Example scenarios for industrial and agriculture fleets.",
            to: "/case-studies",
          },
        ]}
      />
    </MarketingShell>
  );
}

/**
 * `/blog` stays live as a pointer page: the team publishes release notes in
 * the changelog rather than a separate blog, and the cards below say so
 * instead of dressing internal links up as posts.
 */
export function BlogPage() {
  const posts = [
    {
      date: "Release notes",
      title: "Everything we ship",
      excerpt: "The changelog is the published record of product changes — this is where updates go.",
      to: "/changelog",
    },
    {
      date: "Guide",
      title: "MQTT topics & device credentials",
      excerpt: "Topic reference, payload contracts, and sample clients for firmware teams.",
      to: "/developers/mqtt-devices",
    },
    {
      date: "Reference",
      title: "REST API docs",
      excerpt: "JWT auth plus representative endpoints for devices, dashboards, rules, and billing.",
      to: "/docs",
    },
  ];

  return (
    <MarketingShell
      eyebrow="Company"
      title="Product updates & guides"
      subtitle="We publish release notes in the changelog rather than a blog — this page points there and to the developer references."
      image={marketingImages.consoleDesk}
      imageAlt="IoTAPS product updates"
      metaTitle="Product updates & guides"
      metaDescription="Pointers to IoTAPS release notes in the changelog and to the MQTT and REST API references — no separate blog."
      wide
    >
      <MarketingBlogList posts={posts} />
      <MarketingCtaInline title="See every release" to="/changelog" label="Full changelog" />
    </MarketingShell>
  );
}

/**
 * `/case-studies` stays live without published customer stories. The cards
 * below are labelled example scenarios of what the platform does — never
 * customer results — because no named case studies exist in this repo.
 */
export function CaseStudiesPage() {
  return (
    <MarketingShell
      eyebrow="Deployment patterns"
      title="Typical deployment patterns"
      subtitle="Example scenarios describing what the platform does — not customer results. No customer counts or named deployments are claimed here."
      image={marketingImages.solutionsAgriculture}
      imageAlt="IoT deployment patterns"
      metaTitle="IoT deployment patterns"
      metaDescription="Example deployment patterns for industrial monitoring and precision agriculture — what the IoTAPS platform does, without customer counts or named results."
      wide
    >
      <div className="grid gap-6 lg:grid-cols-2">
        {[
          {
            title: "Industrial monitoring",
            body: "Example scenario: plant sensors publish MQTT telemetry on token topics, supervisors watch live dashboards, and rule chains fire alerts when thresholds breach. Organizations, device groups, and console roles keep sites separated.",
            image: marketingImages.industrialPlant,
            to: "/solutions/industrial-iot",
          },
          {
            title: "Precision agriculture",
            body: "Example scenario: greenhouse and soil sensors stream readings to dashboards shared as read-only links, with rule chains scheduled from soil-moisture readings and historical series retained per plan tier.",
            image: marketingImages.solutionsAgriculture,
            to: "/solutions/smart-agriculture",
          },
        ].map((study) => (
          <article key={study.title} className="blynk-platform-card overflow-hidden">
            <MarketingImage src={study.image} alt="" className="aspect-[16/10] w-full" />
            <div className="p-6 sm:p-8">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Example scenario
              </p>
              {/* h2: these cards are the page's content sections under the hero h1. */}
              <h2 className="mt-2 text-lg font-bold uppercase tracking-tight">{study.title}</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{study.body}</p>
              <Link to={study.to} className="mt-4 inline-flex text-sm font-bold text-primary hover:underline">
                View solution →
              </Link>
            </div>
          </article>
        ))}
      </div>
      <MarketingCtaInline title="Talk through your deployment" to="/contact" label="Contact us" />
    </MarketingShell>
  );
}
