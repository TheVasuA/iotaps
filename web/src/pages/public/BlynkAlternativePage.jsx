import { Link } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { MarketingShell, MarketingProse } from "@/components/public/PublicPage";
import {
  MarketingRelatedLinks,
  MarketingCtaInline,
} from "@/pages/public/marketing/createMarketingPage";
import { marketingImages } from "@/lib/marketingImages";

// Capability and evaluation copy below is intentionally limited to behavior that
// exists in this repository (plan limits, MQTT topic layout, roles, exports,
// deployment manifests). No metrics, no competitor comparisons.

const whatIoTapsIs = [
  {
    heading: "An MQTT-native device platform",
    body: [
      "IoTAPS provisions devices that connect over standard MQTT. Each device gets its own token and publishes on iotaps/{token}/{type}, where type is one of telemetry, command, ack, or status. A legacy iotaps/{org_id}/{device_id}/{type} layout is also accepted, and per-organization broker ACLs are restricted to iotaps/{org_id}/#.",
      "Devices speak standard MQTT and exchange JSON payloads on those topics.",
    ],
  },
  {
    heading: "Telemetry storage built for history",
    body: [
      "Readings land in TimescaleDB and are kept for the retention window of your plan. A background downsampler rolls raw samples into hourly aggregates, alongside 5-minute and daily rollups.",
      "You can export any device's telemetry as CSV from the console, and generate one-off CSV or PDF reports from a telemetry query.",
    ],
  },
  {
    heading: "A console that covers the whole loop",
    body: [
      "Device management and MQTT provisioning, drag-and-drop dashboards, a visual rule engine for automation, remote device control over MQTT commands, and subscription billing — all in one place, scoped by organization.",
    ],
  },
  {
    heading: "Deployable on your own infrastructure",
    body: [
      "The repository ships Docker Compose and Kubernetes/Kustomize manifests, so the same stack can run on a single VPS or in a cluster you control. Data, broker, and database stay on infrastructure you own when you self-host.",
    ],
  },
];

const migrationSteps = [
  {
    step: "1. Stand up an organization and provision devices",
    body: "Create your organization in the console and add each device. Provisioning issues a device token, which stands in for the org and device IDs in the device's MQTT topic namespace.",
  },
  {
    step: "2. Re-point firmware at the new broker and topics",
    body: "Update the broker host and credentials in your firmware, then publish telemetry to iotaps/{token}/telemetry, subscribe to iotaps/{token}/command, and report acknowledgements and presence on the ack and status topics. The message types are telemetry, command, ack, and status.",
  },
  {
    step: "3. Rebuild dashboards from the widget palette",
    body: "Recreate each view on the drag-and-drop canvas using the built-in widgets: line, bar, and gauge charts, value readouts, a map, toggles, sliders, and alert badges. Toggles and sliders issue device commands, so controls can be verified as soon as a device is online.",
  },
  {
    step: "4. Move automation into the rule engine",
    body: "Recreate automations as rules with conditions and actions in the visual rule editor. Rule allowances are plan-based (the Free plan includes 2 rules), so complex logic may need to be prioritized.",
  },
  {
    step: "5. Cut over and verify",
    body: "Run both paths briefly if you need to: confirm telemetry is arriving, fire a remote command and watch for its acknowledgement, and export a CSV of a device's history to confirm the data looks right before decommissioning the old stack.",
  },
];

const capabilities = [
  {
    label: "Plans",
    body: "Free: 2 devices, 20,000 messages per month, 7-day retention, 10 sensors, 2 rules, view-only console. Pro: unlimited devices, 90-day retention, volume unit pricing that steps down as device count grows.",
  },
  {
    label: "Security",
    body: "TOTP two-factor authentication with one-time backup codes, and JWT bearer API tokens that carry the caller's organization.",
  },
  {
    label: "Roles",
    body: "Three console roles — super admin, project center, and device user — so fleet operators and end customers see different surfaces.",
  },
  {
    label: "Data portability",
    body: "Per-device CSV export of telemetry, plus generated CSV and PDF reports from telemetry queries.",
  },
  {
    label: "Self-hosting",
    body: "Docker Compose and Kubernetes/Kustomize manifests in the repository, for deployments you run yourself.",
  },
  {
    label: "Refunds",
    body: "A 14-day refund window.",
  },
];

// Buyer questions, not competitor claims. Each one maps to something a reader
// can verify on IoTAPS (linked below or answered on this page).
const evaluationQuestions = [
  {
    q: "Self-host or SaaS?",
    body: "Can you run the platform on your own infrastructure, and are the deployment manifests published? If data residency matters, this decides where your telemetry physically lives.",
  },
  {
    q: "How long is telemetry retained?",
    body: "Ask for the raw-data retention window per plan tier, and whether history beyond that window is available as aggregates. Retention is often the hidden cost in an IoT platform.",
  },
  {
    q: "How is tenant data isolated?",
    body: "Is every organization's data scoped to that organization, including broker access? On IoTAPS, MQTT ACLs restrict each organization's credentials to iotaps/{org_id}/#.",
  },
  {
    q: "What is the role model?",
    body: "Which roles exist, and what can each one see and do? IoTAPS has three: super admin, project center, and device user.",
  },
  {
    q: "How do you get your data out?",
    body: "Per-device CSV export and generated reports mean history is never locked inside the console. Confirm any platform you evaluate offers something equivalent.",
  },
  {
    q: "What does migration actually involve?",
    body: "Ask whether there is a bulk importer for dashboards and automations. For IoTAPS there is not — devices are re-provisioned with new tokens and topics, and dashboards and rules are rebuilt in the console, as outlined above.",
  },
];

export default function BlynkAlternativePage() {
  return (
    <MarketingShell
      eyebrow="Alternative & migration"
      title="Looking for a Blynk alternative?"
      subtitle="IoTAPS is an MQTT-native IoT platform — device provisioning, live dashboards, a visual rule engine, and subscription billing — with Docker Compose or Kubernetes deployments you can run yourself. Here is what the platform does, and what moving onto it involves."
      image={marketingImages.consoleDesk}
      imageAlt="Developer workspace with IoT dashboard screens"
      metaTitle="Blynk alternative: MQTT-native IoT platform you can self-host"
      metaDescription="Evaluating a Blynk alternative? IoTAPS is an MQTT-native IoT platform with self-hosting, plan-based telemetry retention, role-based console access, CSV/PDF export, and a concrete migration path for devices, dashboards, and automation."
      showCta={false}
    >
      <MarketingRelatedLinks
        title="Explore the platform"
        links={[
          { to: "/platform", label: "Platform overview" },
          { to: "/developers/mqtt-devices", label: "MQTT & devices" },
          { to: "/pricing", label: "Pricing" },
          { to: "/docs", label: "Docs / API" },
        ]}
      />

      <MarketingProse sections={whatIoTapsIs} />

      <article className="blynk-platform-card mt-6 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide text-foreground">
          How migration works
        </h2>
        <p className="mt-3 text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
          There is no bulk importer for another platform&rsquo;s projects: dashboards and automations
          are rebuilt by hand in the console. Plan for the rebuild, and use this sequence to keep the
          cutover boring.
        </p>
        <ol className="mt-6 space-y-5">
          {migrationSteps.map((item) => (
            <li key={item.step} className="border-b border-border/60 pb-5 last:border-0 last:pb-0">
              <p className="text-sm font-bold uppercase tracking-wide text-foreground">{item.step}</p>
              <p className="mt-2 text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
                {item.body}
              </p>
            </li>
          ))}
        </ol>
      </article>

      <article className="blynk-platform-card mt-6 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide text-foreground">
          Platform capabilities
        </h2>
        <dl className="mt-5 grid gap-5 sm:grid-cols-2">
          {capabilities.map((item) => (
            <div key={item.label}>
              <dt className="text-xs font-bold uppercase tracking-wider text-primary">{item.label}</dt>
              <dd className="mt-1.5 text-pretty text-sm leading-7 text-muted-foreground">
                {item.body}
              </dd>
            </div>
          ))}
        </dl>
      </article>

      <article className="blynk-platform-card mt-6 p-6 sm:p-8">
        <h2 className="text-lg font-bold uppercase tracking-wide text-foreground">
          What to check when evaluating an alternative
        </h2>
        <p className="mt-3 text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
          Whichever platform you choose, these are the questions worth asking before you commit a
          fleet to it.
        </p>
        <ul className="mt-5 space-y-5">
          {evaluationQuestions.map((item) => (
            <li key={item.q}>
              <p className="text-sm font-bold text-foreground">{item.q}</p>
              <p className="mt-1.5 text-pretty text-sm leading-7 text-muted-foreground">{item.body}</p>
            </li>
          ))}
        </ul>
      </article>

      <p className="mt-8 text-xs leading-5 text-muted-foreground">
        Blynk is a trademark of its respective owner. IoTAPS is not affiliated with, sponsored by, or
        endorsed by Blynk or its owner.
      </p>

      <MarketingCtaInline
        title="Start with a free account"
        to="/register"
        label="Create free account"
      />
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Prefer to talk it through first?{" "}
        <Link
          to="/contact"
          className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
        >
          Contact us
          <ArrowRight size={12} weight="bold" />
        </Link>
      </p>
    </MarketingShell>
  );
}
