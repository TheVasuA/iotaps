import { Link } from "react-router-dom";
import {
  ChartLineUp,
  Cpu,
  FlowArrow,
  ShieldCheck,
  Lightning,
  UsersThree,
} from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

// Public landing page (Task 21.1, Req 31.1). Top-of-funnel marketing page that
// introduces the platform and routes visitors to pricing and sign-up.

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

export default function LandingPage() {
  return (
    <>
      <section className="mx-auto max-w-6xl px-6 py-20 text-center">
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          IoTAPS — IoT Automation Platform Services
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          Provision devices, visualize telemetry, automate behavior, and bill
          your fleet — all from one platform built for India&apos;s device fleets at scale.
        </p>
        <div className="mt-10 flex items-center justify-center gap-3">
          <Link to="/register" className={buttonVariants({ size: "lg" })}>
            Get started free
          </Link>
          <Link
            to="/pricing"
            className={buttonVariants({ variant: "outline", size: "lg" })}
          >
            View pricing
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => {
            const Icon = feature.icon;
            return (
              <Card key={feature.title}>
                <CardHeader>
                  <Icon size={28} className="text-primary" weight="duotone" />
                  <CardTitle className="text-lg">{feature.title}</CardTitle>
                  <CardDescription>{feature.description}</CardDescription>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      </section>
    </>
  );
}
