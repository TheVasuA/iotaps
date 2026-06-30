import { Link } from "react-router-dom";
import {
  ChartLineUp,
  Cpu,
  FlowArrow,
  ShieldCheck,
  Lightning,
  UsersThree,
  CheckCircle,
  ArrowRight,
  QrCode,
  SlidersHorizontal,
  Broadcast,
} from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

// Public landing page (Task 21.1, Req 31.1). Top-of-funnel marketing page that
// introduces the platform and routes visitors to pricing and sign-up.
//
// Structure follows current SaaS landing-page best practice: a clear
// above-the-fold value prop with a high-contrast CTA and trust microcopy, an
// early capability strip for credibility, scannable feature cards, a short
// "how it works" flow, and a closing CTA band. Everything is driven by the
// shared design tokens so the three role themes + dark mode apply automatically.

const features = [
  {
    icon: Cpu,
    title: "Device provisioning",
    description:
      "Provision any IoT device fleet with per-device MQTT credentials and QR onboarding.",
  },
  {
    icon: ChartLineUp,
    title: "Real-time dashboards",
    description:
      "Drag-and-drop widgets backed by live telemetry over WebSocket, under a second from ingest.",
  },
  {
    icon: FlowArrow,
    title: "Visual rule engine",
    description:
      "Build trigger → condition → action → delay automations without writing code.",
  },
  {
    icon: Lightning,
    title: "Remote control",
    description:
      "Send commands, schedules, and OTA updates - queued safely while devices are offline.",
  },
  {
    icon: UsersThree,
    title: "Partner program",
    description:
      "Earn commission on managed devices and reward referrals with free Pro device-months.",
  },
  {
    icon: ShieldCheck,
    title: "Multi-tenant isolation",
    description:
      "Every device, dashboard, and rule is scoped to your organization with strict data isolation.",
  },
];

const stats = [
  { value: "<1s", label: "Telemetry latency" },
  { value: "99.9%", label: "Uptime target" },
  { value: "MQTT", label: "Native protocol" },
  { value: "OTA", label: "Fleet-wide updates" },
];

const steps = [
  {
    icon: QrCode,
    title: "Provision",
    description:
      "Register devices and onboard them in seconds with QR codes and auto-generated MQTT credentials.",
  },
  {
    icon: SlidersHorizontal,
    title: "Visualize & automate",
    description:
      "Drop telemetry widgets onto dashboards and wire up no-code rules to react to your data.",
  },
  {
    icon: Broadcast,
    title: "Control & scale",
    description:
      "Push commands, schedules, and OTA updates across your whole fleet — then bill it from one place.",
  },
];

export default function LandingPage() {
  return (
    <>
      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden">
        {/* Decorative gradient wash + dot grid (purely visual). */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-b from-primary/10 via-background to-background"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-[-10%] -z-0 h-[420px] w-[680px] -translate-x-1/2 rounded-full bg-primary/20 blur-[120px]"
        />
        <div className="relative mx-auto max-w-6xl px-6 py-20 text-center sm:py-28">
          <span className="mx-auto inline-flex items-center gap-2 rounded-full border border-border bg-card/70 px-4 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur">
            <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
            Built for India&apos;s device fleets at scale
          </span>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold tracking-tight text-foreground sm:text-6xl">
            One platform to{" "}
            <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
              provision, visualize, and automate
            </span>{" "}
            your IoT fleet
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
            IoTAPS brings device provisioning, live telemetry dashboards, no-code
            automation, and fleet billing together — so you can ship connected
            products without stitching tools together.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link to="/register" className={buttonVariants({ size: "lg" })}>
              Get started free
              <ArrowRight size={18} weight="bold" />
            </Link>
            <Link
              to="/pricing"
              className={buttonVariants({ variant: "outline", size: "lg" })}
            >
              View pricing
            </Link>
          </div>
          <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
            {["No credit card required", "Free tier to start", "Cancel anytime"].map(
              (item) => (
                <li key={item} className="inline-flex items-center gap-1.5">
                  <CheckCircle size={16} weight="fill" className="text-secondary" />
                  {item}
                </li>
              )
            )}
          </ul>

          {/* Capability strip — credibility without fabricated social proof. */}
          <dl className="mx-auto mt-16 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
            {stats.map((stat) => (
              <div key={stat.label} className="bg-card px-4 py-5">
                <dt className="text-2xl font-bold text-foreground sm:text-3xl">
                  {stat.value}
                </dt>
                <dd className="mt-1 text-xs text-muted-foreground">{stat.label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---- Features ---- */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Everything your fleet needs, in one place
          </h2>
          <p className="mt-3 text-muted-foreground">
            From the first device to the millionth message, IoTAPS scales with you.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <Card
                key={feature.title}
                className="group transition-all hover:-translate-y-1 hover:border-primary/40 hover:shadow-md"
              >
                <CardHeader>
                  <span className="mb-2 inline-flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                    <Icon size={24} weight="duotone" />
                  </span>
                  <CardTitle className="text-lg">{feature.title}</CardTitle>
                  <CardDescription>{feature.description}</CardDescription>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section className="border-t border-border bg-muted/30">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-foreground">
              Live in three steps
            </h2>
            <p className="mt-3 text-muted-foreground">
              No infrastructure to manage — connect your devices and go.
            </p>
          </div>
          <ol className="grid gap-8 md:grid-cols-3">
            {steps.map((step, index) => {
              const Icon = step.icon;
              return (
                <li key={step.title} className="relative text-center">
                  <span className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-full border border-border bg-card text-primary shadow-sm">
                    <Icon size={26} weight="duotone" />
                  </span>
                  <h3 className="mt-4 flex items-center justify-center gap-2 text-lg font-semibold text-foreground">
                    <span className="text-sm font-bold text-muted-foreground">
                      {index + 1}.
                    </span>
                    {step.title}
                  </h3>
                  <p className="mx-auto mt-2 max-w-xs text-sm text-muted-foreground">
                    {step.description}
                  </p>
                </li>
              );
            })}
          </ol>
        </div>
      </section>

      {/* ---- Closing CTA ---- */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="relative overflow-hidden rounded-2xl border border-border bg-card px-6 py-14 text-center shadow-sm">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/10 to-secondary/10"
          />
          <div className="relative">
            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight text-foreground">
              Ready to bring your devices online?
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
              Start free, invite your team, and connect your first device in
              minutes. Upgrade only when your fleet grows.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link to="/register" className={buttonVariants({ size: "lg" })}>
                Get started free
                <ArrowRight size={18} weight="bold" />
              </Link>
              <Link
                to="/docs"
                className={buttonVariants({ variant: "outline", size: "lg" })}
              >
                Read the docs
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
