import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Cpu,
  Broadcast,
  SquaresFour,
  FlowArrow,
  Code,
  BookOpen,
  Headset,
  Buildings,
  UsersThree,
  ShieldCheck,
  CreditCard,
  ChartLine,
  ArrowRight,
  CheckCircle,
  Circle,
  Lightning,
  Gear,
  Gift,
} from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectUser } from "@/store/authSlice";
import { fetchDevices, selectDevices } from "@/store/devicesSlice";
import { fetchDashboards, selectDashboards } from "@/store/dashboardsSlice";
import { getPlans } from "@/lib/billingApi";
import { getOrgProfile } from "@/lib/orgApi";
import { ACCOUNT_COMPANY, canManageOrgUsers } from "@/lib/accountTypes";

function accountLabel(type) {
  if (type === ACCOUNT_COMPANY) return "Company workspace";
  if (type === "student") return "Student workspace";
  return "Individual workspace";
}

function MetricTile({ icon: Icon, label, used, limit, hint }) {
  const pct =
    limit && limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : used > 0 ? 100 : 0;
  const limitLabel = limit == null ? "Unlimited" : limit.toLocaleString();

  return (
    <div className="gs-metric-tile">
      <div className="flex items-center gap-2">
        <span className="gs-metric-icon">
          <Icon size={20} weight="duotone" />
        </span>
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      </div>
      <p className="mt-3 text-2xl font-bold tabular-nums text-foreground">
        {used.toLocaleString()}
        <span className="text-base font-normal text-muted-foreground"> / {limitLabel}</span>
      </p>
      {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
      <div className="gs-metric-bar mt-3" aria-hidden>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

const JOURNEY = [
  {
    id: "device",
    step: 1,
    title: "Connect a device",
    body: "Create credentials, assign MQTT topics, and see your first telemetry in the explorer.",
    to: "/devices",
    cta: "Devices",
    icon: Cpu,
  },
  {
    id: "dashboard",
    step: 2,
    title: "Build a dashboard",
    body: "Add charts, gauges, and controls bound to live device data.",
    to: "/dashboard",
    cta: "Dashboards",
    icon: SquaresFour,
  },
  {
    id: "rules",
    step: 3,
    title: "Automate with rules",
    body: "React to thresholds, schedule actions, and call webhooks from the flow editor.",
    to: "/rules",
    cta: "Automations",
    icon: FlowArrow,
  },
  {
    id: "security",
    step: 4,
    title: "Secure your account",
    body: "Turn on two-factor authentication and review account settings.",
    to: "/settings?tab=security",
    cta: "Security",
    icon: ShieldCheck,
  },
];

const EXPLORE = [
  {
    title: "Live MQTT explorer",
    description: "Subscribe to topics and inspect payloads without a desktop client.",
    to: "/explorer",
    icon: Broadcast,
  },
  {
    title: "Developer zone",
    description: "Web flasher, firmware samples, and serial provisioning tools.",
    to: "/flasher",
    icon: Code,
  },
  {
    title: "Custom data & tables",
    description: "Store and query structured telemetry alongside device streams.",
    to: "/custom-data",
    icon: ChartLine,
  },
  {
    title: "Billing & plans",
    description: "Compare Free and Pro limits, referrals, and upgrade paths.",
    to: "/billing",
    icon: CreditCard,
  },
  {
    title: "Support & help",
    description: "Chat with support and browse troubleshooting guides.",
    to: "/support",
    icon: Headset,
  },
  {
    title: "Referrals",
    description: "Invite friends and earn device-month credits on eligible plans.",
    to: "/referrals",
    icon: Gift,
  },
];

const LEARN = [
  { label: "Documentation", to: "/docs", icon: BookOpen },
  { label: "Pricing for teams", to: "/pricing", icon: Buildings },
  { label: "Product changelog", to: "/changelog", icon: Lightning },
];

export default function GetStartedPage() {
  const dispatch = useAppDispatch();
  const user = useAppSelector(selectUser);
  const devices = useAppSelector(selectDevices);
  const dashboards = useAppSelector(selectDashboards);
  const [plans, setPlans] = useState(null);
  const [orgProfile, setOrgProfile] = useState(null);

  useEffect(() => {
    dispatch(fetchDevices({}));
    dispatch(fetchDashboards());
    getPlans()
      .then(setPlans)
      .catch(() => setPlans(null));
    getOrgProfile()
      .then(setOrgProfile)
      .catch(() => setOrgProfile(null));
  }, [dispatch]);

  const deviceCount = devices.length;
  const dashboardCount = dashboards.length;
  const maxDevices = plans?.free?.max_devices ?? 5;
  const maxMessages = plans?.free?.max_messages_per_month ?? 100_000;
  const maxDashboards = 10;
  const memberCount = orgProfile?.member_count ?? 1;
  const memberLimit = user?.account_type === ACCOUNT_COMPANY ? 50 : 1;

  const displayName = useMemo(() => {
    if (user?.email) {
      const local = user.email.split("@")[0];
      return local.charAt(0).toUpperCase() + local.slice(1);
    }
    return "there";
  }, [user?.email]);

  const progress = useMemo(() => {
    let done = 0;
    if (deviceCount > 0) done += 1;
    if (dashboardCount > 0) done += 1;
    return { done, total: JOURNEY.length };
  }, [deviceCount, dashboardCount]);

  const stepDone = (id) => {
    if (id === "device") return deviceCount > 0;
    if (id === "dashboard") return dashboardCount > 0;
    return false;
  };

  return (
    <div className="console-get-started gs-screen">
      <section className="gs-hero gs-hero-full">
        <div className="gs-hero-grid" aria-hidden />
        <div className="gs-hero-inner">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-primary">
                IoTAPS Console
              </p>
              <h1 className="mt-2 font-brand text-3xl font-bold tracking-tight text-foreground md:text-4xl">
                Welcome back, {displayName}
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground md:text-base">
                Your control center for devices, live data, dashboards, and automations — hosted on
                your IoTAPS workspace with MQTT, rules, and billing in one place.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge variant="secondary">{accountLabel(user?.account_type)}</Badge>
                {user?.organization_name ? (
                  <Badge variant="outline">{user.organization_name}</Badge>
                ) : null}
                <Badge variant="outline">Free plan</Badge>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link to="/devices" className={cn(buttonVariants(), "font-semibold shadow-sm")}>
                <Cpu size={18} className="mr-2" weight="bold" />
                Add device
              </Link>
              <Link
                to="/dashboard"
                className={cn(buttonVariants({ variant: "outline" }), "font-semibold")}
              >
                Open dashboards
              </Link>
              <Link
                to="/settings"
                className={cn(buttonVariants({ variant: "ghost" }), "font-semibold")}
              >
                <Gear size={18} className="mr-1" />
                Account
              </Link>
            </div>
          </div>
        </div>
      </section>

      <div className="gs-screen-body">
        <section className="gs-section" aria-labelledby="usage-heading">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h2 id="usage-heading" className="text-sm font-bold text-foreground">
              Workspace usage
            </h2>
            <Link to="/billing" className="text-xs font-semibold text-primary hover:underline">
              View plans & billing
            </Link>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricTile icon={Cpu} label="Devices" used={deviceCount} limit={maxDevices} />
            <MetricTile
              icon={Broadcast}
              label="Messages (month)"
              used={0}
              limit={maxMessages}
              hint="Resets each billing period"
            />
            <MetricTile icon={SquaresFour} label="Dashboards" used={dashboardCount} limit={maxDashboards} />
            <MetricTile
              icon={UsersThree}
              label="Team members"
              used={memberCount}
              limit={memberLimit}
              hint={
                canManageOrgUsers(user)
                  ? "Invite users from Organization → Users"
                  : "Upgrade to company to invite teammates"
              }
            />
          </div>
        </section>

        <section className="gs-section" aria-labelledby="journey-heading">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 id="journey-heading" className="text-lg font-bold text-foreground">
                  Your setup journey
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {progress.done} of {progress.total} recommended steps started — pick up where you
                  left off.
                </p>
              </div>
              <div className="gs-progress-ring" aria-hidden>
                <span>{Math.round((progress.done / progress.total) * 100)}%</span>
              </div>
            </div>
            <ol className="mt-6 grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
              {JOURNEY.map((item) => {
                const done = stepDone(item.id);
                const Icon = item.icon;
                return (
                  <li key={item.id} className={cn("gs-journey-card", done && "gs-journey-card-done")}>
                    <div className="flex items-start gap-4">
                      <span className="gs-journey-step-num">{item.step}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Icon size={20} weight="duotone" className="text-primary" />
                          <h3 className="font-semibold text-foreground">{item.title}</h3>
                          {done ? (
                            <CheckCircle size={18} weight="fill" className="ml-auto text-primary" />
                          ) : (
                            <Circle size={18} className="ml-auto text-muted-foreground/50" />
                          )}
                        </div>
                        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                          {item.body}
                        </p>
                        <Link
                          to={item.to}
                          className="mt-3 inline-flex items-center gap-1 text-sm font-bold text-primary hover:underline"
                        >
                          {item.cta}
                          <ArrowRight size={14} weight="bold" />
                        </Link>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
        </section>

        {canManageOrgUsers(user) ? (
          <section className="gs-section gs-company-banner">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-base font-bold text-foreground">Organization admin</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Add operators and device users to your company workspace — same model as multi-seat
                  IoT consoles.
                </p>
              </div>
              <Link
                to="/org/users"
                className={cn(buttonVariants({ variant: "outline" }), "shrink-0 font-semibold")}
              >
                <UsersThree size={18} className="mr-2" />
                Manage users
              </Link>
            </div>
          </section>
        ) : null}

        <section className="gs-section" aria-labelledby="explore-heading">
          <h2 id="explore-heading" className="text-lg font-bold text-foreground">
            Explore the console
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Everything in the sidebar — grouped by what teams use most after onboarding.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {EXPLORE.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.title} to={item.to} className="gs-explore-card group">
                  <span className="gs-explore-icon">
                    <Icon size={22} weight="duotone" />
                  </span>
                  <h3 className="mt-3 text-sm font-bold text-foreground group-hover:text-primary">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 flex-1 text-xs leading-relaxed text-muted-foreground">
                    {item.description}
                  </p>
                  <span className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-primary opacity-0 transition group-hover:opacity-100">
                    Open <ArrowRight size={12} />
                  </span>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="gs-section grid gap-4 lg:grid-cols-3" aria-labelledby="learn-heading">
          <div className="lg:col-span-2 gs-learn-panel">
            <h2 id="learn-heading" className="text-base font-bold text-foreground">
              Learn & grow
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              IoTAPS runs your MQTT broker, time-series storage, rule engine, and dashboards together.
              Start with the docs for provisioning ESP32 and Raspberry Pi devices, then explore
              public dashboards and referral credits on Pro.
            </p>
            <ul className="mt-4 flex flex-wrap gap-3">
              {LEARN.map(({ label, to, icon: Icon }) => (
                <li key={to}>
                  <Link
                    to={to}
                    className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm font-medium transition hover:border-primary/40 hover:text-primary"
                  >
                    <Icon size={18} weight="duotone" className="text-primary" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="gs-support-panel">
            <Headset size={28} weight="duotone" className="text-primary" />
            <h3 className="mt-3 text-sm font-bold">Need a hand?</h3>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Support threads include your workspace context — devices, billing, and integrations.
            </p>
            <Link
              to="/support"
              className={cn(buttonVariants({ size: "sm" }), "mt-4 w-full font-semibold")}
            >
              Open support
            </Link>
          </div>
        </section>

        <footer className="gs-screen-footer flex flex-wrap gap-4 border-t border-border pt-6 text-xs text-muted-foreground">
          <Link to="/privacy" className="hover:text-foreground">
            Privacy
          </Link>
          <Link to="/terms" className="hover:text-foreground">
            Terms
          </Link>
          <Link to="/status" className="hover:text-foreground">
            Platform status
          </Link>
          <span className="ml-auto">IoTAPS Console · Get started</span>
        </footer>
      </div>
    </div>
  );
}

export function GetStartedOrgBar() {
  const user = useAppSelector(selectUser);
  const orgLabel = user?.organization_name || user?.email?.split("@")[1] || "My workspace";

  return (
    <button
      type="button"
      className="hidden max-w-[min(100%,240px)] items-center gap-1 truncate rounded-md border border-border bg-card px-2.5 py-1.5 text-sm font-medium text-foreground hover:bg-muted/50 md:flex"
    >
      <span className="truncate">{orgLabel}</span>
    </button>
  );
}

export function GetStartedTopActions({ messageLimit = 100_000 }) {
  return (
    <div className="mr-1 hidden items-center gap-3 lg:flex">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="whitespace-nowrap">Messages</span>
        <span className="font-medium text-foreground">0</span>
        <span>/ {messageLimit >= 1000 ? `${(messageLimit / 1000).toFixed(0)}k` : messageLimit}</span>
      </div>
      <Link
        to="/support"
        className={cn(buttonVariants({ size: "sm" }), "h-8 rounded-md px-3 text-xs font-bold")}
      >
        Help
      </Link>
    </div>
  );
}
