import { Link } from "react-router-dom";
import {
  ArrowRight,
  Play,
  DeviceMobile,
  Desktop,
  Cloud,
  PlugsConnected,
  CheckCircle,
} from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import ProductPreview from "@/components/public/ProductPreview";
import { MarketingImage } from "@/components/public/MarketingSubpage";
import { landingImageMap, marketingImages } from "@/lib/marketingImages";
import { Reveal, RevealStagger, RevealItem } from "@/components/public/blynk/LandingReveal";
import { BlynkEyebrow, BlynkSectionTitle } from "@/components/public/blynk/BlynkTypography";

// Re-exported for existing importers. Prefer @/components/public/blynk/BlynkTypography
// in new code: importing the typography from here pulls LandingReveal and with
// it the framer-motion vendor chunk.
export { BlynkEyebrow, BlynkSectionTitle };

const platformPillars = [
  {
    icon: DeviceMobile,
    title: "Mobile-ready",
    description: "Responsive dashboards and device views that work on phones and tablets.",
    to: "/docs",
  },
  {
    icon: Desktop,
    title: "Web console",
    description: "Control fleets, dashboards, and automations from one secure console.",
    to: "/register",
  },
  {
    icon: Cloud,
    title: "Managed cloud",
    description: "Multi-tenant hosting with MQTT ingest, WebSocket telemetry, and billing.",
    to: "/about",
  },
  {
    icon: PlugsConnected,
    title: "MQTT & APIs",
    description: "Connect hardware with MQTT credentials, REST, and webhooks.",
    to: "/docs",
  },
];

const complexityCards = [
  {
    title: "Build without coding",
    body: "Drag-and-drop dashboards and a visual rule engine — trigger, condition, action, delay.",
  },
  {
    title: "Fleet & user management",
    body: "Organizations, roles, device groups, and scoped access for every tenant.",
    dark: true,
  },
  {
    title: "Real-time telemetry",
    body: "Live widgets backed by WebSocket streams, with telemetry landing on the dashboard as it arrives.",
  },
  {
    title: "Protocols & integrations",
    body: "MQTT-native device paths plus HTTP APIs for apps and partner systems.",
    dark: true,
  },
  {
    title: "Bring your own hardware",
    body: "Any MCU or gateway that speaks MQTT — provision with QR and per-device keys.",
  },
  {
    title: "Scalable infrastructure",
    body: "Designed for fleet growth: workers, WS tier, and observability built in.",
    dark: true,
  },
  {
    title: "OTA & remote control",
    body: "Queue commands and firmware jobs safely while devices are offline.",
  },
  {
    title: "Device provisioning",
    body: "Onboard in minutes with auto-generated credentials and maintenance modes.",
    dark: true,
  },
];

const infraBlocks = [
  {
    title: "Console with your branding",
    body: "White-label friendly console experience with purple-accent CTAs and org isolation.",
    to: "/register",
  },
  {
    title: "Documentation & API",
    body: "Open docs for devices, dashboards, rules, and billing — ship integrations faster.",
    to: "/docs",
  },
  {
    title: "Ready-to-use platform stack",
    body: "Skip building ingest, tenancy, and automation — focus on your product.",
    to: "/pricing",
  },
  {
    title: "Grow with Pro & partners",
    body: "Volume pricing, referrals, and partner commissions as fleets scale.",
    to: "/pricing",
  },
];

const showcaseScreens = [
  {
    label: "Fleet overview",
    image: marketingImages.fleetLogistics,
    alt: "Logistics fleet monitoring",
  },
  {
    label: "Live dashboards",
    image: marketingImages.analyticsDashboard,
    alt: "Real-time analytics dashboards",
  },
  {
    label: "Field devices",
    image: marketingImages.solutionsAgriculture,
    alt: "Connected agriculture sensors",
  },
  {
    label: "Industrial IoT",
    image: marketingImages.industrialPlant,
    alt: "Manufacturing automation",
  },
  {
    label: "Energy & utilities",
    image: marketingImages.energyGrid,
    alt: "Solar and smart grid monitoring",
  },
];

// "Cancel anytime" is out: no self-serve cancel flow exists yet. The refund
// window is real (refund_window_days: 14 in app/core/settings_loader.py).
const trustItems = ["No credit card", "Free tier", "MQTT native", "14-day refund"];

export function SolutionsGallery() {
  return (
    <section className="landing-section bg-background">
      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="mx-auto max-w-3xl text-center">
          <BlynkEyebrow>Solutions</BlynkEyebrow>
          <BlynkSectionTitle className="mt-4">
            From factory floor to field — one platform
          </BlynkSectionTitle>
          <p className="mt-4 text-pretty text-muted-foreground">
            Industrial monitoring, smart agriculture, and consumer fleets share the same console,
            rules, and billing layer.
          </p>
        </Reveal>
        <div className="mt-12 grid gap-4 lg:grid-cols-12 lg:gap-5">
          <Reveal className="marketing-split-image lg:col-span-7 lg:row-span-2">
            <MarketingImage
              src={landingImageMap.solutionsHero}
              alt="Industrial automation and connected manufacturing"
              className="aspect-[16/10] min-h-[260px]"
            />
          </Reveal>
          <Reveal delay={0.08} className="marketing-split-image lg:col-span-5">
            <MarketingImage
              src={landingImageMap.solutionsAccent}
              alt="Greenhouse IoT monitoring with connected sensors"
              className="aspect-[4/3] min-h-[200px]"
            />
          </Reveal>
          <Reveal delay={0.12} className="blynk-platform-card flex flex-col justify-center p-8 lg:col-span-5">
            <h3 className="text-lg font-bold uppercase tracking-tight">Field to HQ visibility</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Pair QR provisioning with live dashboards so field teams and HQ see the same telemetry
              within seconds of device connect.
            </p>
            <Link
              to="/about"
              className="mt-6 inline-flex items-center gap-2 text-sm font-bold uppercase hover:text-primary"
            >
              Explore use cases <ArrowRight size={16} weight="bold" />
            </Link>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

export function LogoMarquee() {
  const logos = [
    "Industrial OEMs",
    "Smart agriculture",
    "Energy & HVAC",
    "Fleet logistics",
    "Consumer IoT",
    "System integrators",
  ];
  const track = [...logos, ...logos];

  return (
    <section className="landing-section border-y border-border bg-[#fafafa] py-10 dark:bg-muted/20">
      <div className="mx-auto max-w-7xl px-6">
        <p className="text-center text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
          Built for teams shipping connected hardware
        </p>
        <div className="blynk-marquee-mask relative mt-6 overflow-hidden">
          <div className="blynk-marquee-track flex w-max gap-12">
            {track.map((name, i) => (
              <span
                key={`${name}-${i}`}
                className="whitespace-nowrap text-sm font-semibold uppercase tracking-widest text-foreground/60"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

const heroMetrics = [
  // No latency figure: nothing in the repo benchmarks one, and the batch-writer
  // ingest path can exceed a second under load.
  { value: "Live", label: "Telemetry streaming", hint: "WebSocket to dashboard" },
  { value: "Self-host", label: "Your infra or ours", hint: "Docker & Kubernetes" },
  { value: "MQTT", label: "Native protocol", hint: "Per-device keys" },
  { value: "OTA", label: "Fleet updates", hint: "Commands & jobs" },
];

export function LandingHero() {
  return (
    <section className="blynk-hero blynk-hero-mesh relative overflow-hidden">
      <div aria-hidden className="blynk-hero-noise pointer-events-none absolute inset-0 opacity-[0.35]" />
      <div className="relative mx-auto max-w-7xl px-6 pb-12 pt-16 sm:pb-20 sm:pt-20 lg:pb-24 lg:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:gap-16">
          <Reveal className="text-center lg:text-left">
            <BlynkEyebrow>Low-code IoT platform</BlynkEyebrow>
            <h1 className="landing-hero-title mt-5 font-brand font-bold uppercase tracking-tight text-white lg:mt-6">
              Ship connected hardware with{" "}
              <span className="blynk-highlight-word">one console</span> for fleet, data &amp; apps
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-pretty text-base leading-[1.7] text-white/65 sm:text-lg lg:mx-0">
              Connect devices over MQTT, build dashboards and automations, and scale tenants — without
              rebuilding cloud infrastructure.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row lg:justify-start">
              <Link
                to="/register"
                className={cn(
                  buttonVariants({ size: "lg" }),
                  "landing-cta-primary min-w-[200px] px-8 shadow-[0_0_0_1px_rgba(0,0,0,0.2)]"
                )}
              >
                Get started
                <ArrowRight size={18} weight="bold" />
              </Link>
              <Link
                to="/contact"
                className={buttonVariants({
                  variant: "outline",
                  size: "lg",
                  className:
                    "min-w-[200px] border-white/25 bg-white/[0.04] px-8 text-white backdrop-blur-sm hover:bg-white/10 hover:text-white",
                })}
              >
                Enterprise solutions
              </Link>
            </div>
            <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 lg:justify-start">
              {trustItems.map((item) => (
                <li key={item} className="inline-flex items-center gap-1.5 text-xs text-white/55">
                  <CheckCircle size={14} weight="fill" className="text-primary" />
                  {item}
                </li>
              ))}
            </ul>
            <Link
              to="/docs"
              className="group mt-8 inline-flex items-center gap-4 rounded-lg border border-white/10 bg-white/[0.04] px-5 py-3.5 text-left transition-colors hover:border-white/20 hover:bg-white/[0.07]"
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/25 transition-transform group-hover:scale-105">
                <Play size={20} weight="fill" />
              </span>
              <span>
                <span className="block text-[10px] font-bold uppercase tracking-[0.2em] text-white/60">
                  Platform tour
                </span>
                <span className="text-sm font-semibold text-white">Docs · devices · dashboards</span>
              </span>
            </Link>
          </Reveal>

          <Reveal delay={0.08} className="landing-metric-panel mx-auto w-full max-w-md lg:max-w-none">
            <p className="mb-4 text-center text-[10px] font-bold uppercase tracking-[0.22em] text-white/60 lg:text-left">
              Built for production fleets
            </p>
            <ul className="landing-metric-list divide-y divide-white/10 rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-sm">
              {heroMetrics.map((stat) => (
                <li key={stat.label} className="flex items-center gap-4 px-5 py-4">
                  <span className="landing-metric-value shrink-0 tabular-nums">{stat.value}</span>
                  <div className="min-w-0 text-left">
                    <p className="text-sm font-semibold text-white">{stat.label}</p>
                    <p className="text-xs text-white/60">{stat.hint}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>

        <Reveal delay={0.12}>
          <ProductPreview />
        </Reveal>
      </div>
    </section>
  );
}

export function PlatformExplore() {
  return (
    <section className="landing-section bg-background">
      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-xl">
            <BlynkEyebrow>Explore the platform</BlynkEyebrow>
            <BlynkSectionTitle className="mt-4">
              Mobile apps, web console, cloud & connectivity
            </BlynkSectionTitle>
            <p className="mt-4 text-pretty text-base leading-relaxed text-muted-foreground">
              We designed the building blocks of a complete IoT stack so your team ships product
              instead of reinventing infrastructure.
            </p>
          </div>
          <Link
            to="/docs"
            className={cn(buttonVariants({ variant: "outline" }), "shrink-0 self-start lg:self-auto")}
          >
            Read documentation
          </Link>
        </Reveal>

        <RevealStagger className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {platformPillars.map(({ icon: Icon, title, description, to }, index) => (
            <RevealItem key={title}>
              <Link to={to} className="blynk-platform-card group flex h-full flex-col p-7">
                <span className="text-[10px] font-bold tabular-nums text-muted-foreground/80">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <Icon
                  size={32}
                  weight="duotone"
                  className="mt-4 text-foreground transition-colors duration-300 group-hover:text-primary"
                />
                <h3 className="mt-5 text-sm font-bold uppercase tracking-wide">{title}</h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                  {description}
                </p>
                <span className="mt-6 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide opacity-80 transition-all group-hover:gap-2.5 group-hover:text-primary group-hover:opacity-100">
                  Learn more <ArrowRight size={14} weight="bold" />
                </span>
              </Link>
            </RevealItem>
          ))}
        </RevealStagger>
      </div>
    </section>
  );
}

export function FeaturedInsights() {
  return (
    <section className="landing-section blynk-section-alt">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-5 lg:grid-cols-12 lg:gap-6">
          <Reveal className="lg:col-span-7">
            <article className="blynk-featured-card group relative h-full overflow-hidden">
              <div className="blynk-featured-accent h-1.5 w-full" />
              <div className="grid lg:grid-cols-[1fr_200px]">
                <div className="p-8 sm:p-10">
                  <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">
                    Featured
                  </p>
                  <h2 className="mt-4 text-2xl font-bold leading-snug tracking-tight sm:text-3xl">
                    Visual rule engine: automate fleets without shipping new firmware
                  </h2>
                  <p className="mt-4 max-w-xl text-pretty text-sm leading-relaxed text-muted-foreground sm:text-base">
                    Wire triggers to telemetry thresholds, schedules, and device commands. Deploy
                    rule chains with a Node-RED-style editor and persistent debug logs.
                  </p>
                  <Link
                    to="/docs"
                    className="mt-8 inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wide transition-colors hover:text-primary"
                  >
                    Read in docs <ArrowRight size={16} weight="bold" />
                  </Link>
                </div>
                <div className="relative hidden min-h-[240px] lg:block">
                  <MarketingImage
                    src={landingImageMap.featuredRuleEngine}
                    alt="Analytics and dashboard screens for IoT telemetry"
                    className="absolute inset-0 aspect-auto min-h-full"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
                </div>
              </div>
            </article>
          </Reveal>
          <div className="flex flex-col gap-5 lg:col-span-5">
            <Reveal delay={0.08}>
              <article className="blynk-platform-card flex-1 p-7">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                  Changelog
                </p>
                <h2 className="mt-3 text-lg font-bold leading-snug">
                  Dashboard canvas with drag-and-drop widgets
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  Widget library, 12-column grid, debounced layout saves, and mobile preview.
                </p>
                <Link
                  to="/changelog"
                  className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-sky-600 hover:underline dark:text-sky-400"
                >
                  See what&apos;s new
                </Link>
              </article>
            </Reveal>
            <Reveal delay={0.14}>
              <article className="blynk-platform-card flex-1 p-7">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                  Developers
                </p>
                <h2 className="mt-3 text-lg font-bold leading-snug">
                  MQTT provisioning & device credentials
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  QR onboarding, entity tabs, RPC, events, and fleet maintenance modes.
                </p>
                <Link
                  to="/docs"
                  className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-sky-600 hover:underline dark:text-sky-400"
                >
                  API reference
                </Link>
              </article>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ComplexityGrid() {
  return (
    <section className="landing-section">
      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="mx-auto max-w-3xl text-center">
          <BlynkSectionTitle>
            IoT complexity
            <span className="mt-2 block text-muted-foreground">solved at every stage</span>
          </BlynkSectionTitle>
        </Reveal>
        <RevealStagger className="mt-14 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 lg:gap-3">
          {complexityCards.map((card) => (
            <RevealItem key={card.title}>
              <article
                className={cn(
                  "blynk-complexity-card group min-h-[190px] p-6 transition-transform duration-300 hover:-translate-y-0.5 lg:p-7",
                  card.dark ? "blynk-complexity-dark" : "blynk-complexity-light"
                )}
              >
                <div
                  className={cn(
                    "mb-4 h-0.5 w-8 transition-all duration-300 group-hover:w-12",
                    card.dark ? "bg-primary" : "bg-foreground"
                  )}
                />
                <h3 className="text-sm font-bold uppercase leading-snug tracking-wide">
                  {card.title}
                </h3>
                <p
                  className={cn(
                    "mt-3 text-sm leading-relaxed",
                    card.dark ? "text-white/60" : "text-muted-foreground"
                  )}
                >
                  {card.body}
                </p>
              </article>
            </RevealItem>
          ))}
        </RevealStagger>
      </div>
    </section>
  );
}

export function TestimonialSection() {
  return (
    <section className="landing-section blynk-section-alt">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-center">
          <Reveal className="lg:col-span-5">
            <div className="marketing-split-image relative mx-auto max-w-md lg:mx-0">
              <MarketingImage
                src={landingImageMap.testimonial}
                alt="Energy and utilities IoT deployment"
                className="aspect-[4/5] min-h-[320px]"
              />
            </div>
          </Reveal>
          <Reveal delay={0.1} className="lg:col-span-7">
            <BlynkEyebrow>In practice</BlynkEyebrow>
            <BlynkSectionTitle className="mt-4 max-w-2xl">
              One console from provisioning to billing
            </BlynkSectionTitle>
            {/* Plain summary panel — not blynk-quote-card, which reads as a
                customer testimonial. Keep attribution out unless one is real. */}
            <div className="mt-8 rounded-xl border border-border bg-muted/30 p-8 sm:p-10">
              <p className="text-pretty text-lg leading-relaxed sm:text-xl">
                Teams connect hardware over MQTT, watch live telemetry on dashboards, automate
                responses with rule chains, and manage subscriptions in the same tenant-scoped
                console.
              </p>
              <div className="mt-8 flex flex-wrap gap-3 border-t border-border pt-6">
                <Link to="/case-studies" className={buttonVariants({ variant: "outline", size: "sm" })}>
                  Deployment patterns
                </Link>
                <Link to="/contact" className={buttonVariants({ size: "sm" })}>
                  Talk to us
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

export function AppShowcaseStrip() {
  const highlights = [
    {
      title: "Get started home",
      body: "Onboarding checklist, plan usage, and shortcuts — everything a team needs on day one.",
      image: landingImageMap.showcaseGetStarted,
      alt: "IoTAPS console on a developer desk",
      to: "/register",
      cta: "Create account",
    },
    {
      title: "Fleet & logistics",
      body: "Monitor warehouses, vehicles, and assets from one tenant-scoped workspace.",
      image: landingImageMap.showcaseFleet,
      alt: "Logistics and fleet monitoring",
      to: "/about",
      cta: "See solutions",
    },
    {
      title: "Live dashboards",
      body: "Drag-and-drop widgets, shared links, and WebSocket telemetry your customers see in real time.",
      image: landingImageMap.showcaseDashboards,
      alt: "Analytics dashboards for IoT data",
      to: "/docs",
      cta: "Widget docs",
    },
  ];

  return (
    <section className="landing-showcase-section border-y border-border bg-[#f6f6f8] py-16 dark:bg-muted/20 sm:py-20">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,340px)_1fr] lg:items-end lg:gap-14">
          <Reveal>
            <BlynkEyebrow>Console preview</BlynkEyebrow>
            <BlynkSectionTitle className="mt-4">
              Dashboards &amp; control surfaces built for your brand
            </BlynkSectionTitle>
            <p className="mt-4 text-pretty text-sm leading-relaxed text-muted-foreground sm:text-base">
              Purple-accent CTAs and white-label friendly layouts across the console surfaces —
              shown here with illustrative product imagery.
            </p>
            <Link
              to="/register"
              className={cn(buttonVariants({ size: "lg" }), "mt-8 inline-flex")}
            >
              Try the console
              <ArrowRight size={18} weight="bold" />
            </Link>
          </Reveal>

          <Reveal delay={0.06} className="landing-showcase-bento grid gap-4 sm:grid-cols-2">
            {highlights.map((item, index) => (
              <article
                key={item.title}
                className={cn(
                  "landing-showcase-tile group overflow-hidden rounded-xl border border-border bg-card shadow-sm",
                  index === 0 && "sm:col-span-2 sm:grid sm:grid-cols-2 sm:items-stretch"
                )}
              >
                <div className={cn("relative overflow-hidden", index === 0 ? "min-h-[200px] sm:min-h-full" : "aspect-[4/3]")}>
                  <MarketingImage
                    src={item.image}
                    alt={item.alt}
                    className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-80" />
                </div>
                <div className="flex flex-col p-5 sm:p-6">
                  <h3 className="text-sm font-bold uppercase tracking-wide text-foreground">{item.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
                  <Link
                    to={item.to}
                    className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold text-primary hover:underline"
                  >
                    {item.cta}
                    <ArrowRight size={14} weight="bold" />
                  </Link>
                </div>
              </article>
            ))}
          </Reveal>
        </div>

        <Reveal delay={0.1} className="mt-12">
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card px-5 py-4 shadow-sm sm:px-6">
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Mobile-ready</span> — responsive console
              and device views on phones and tablets.
            </p>
            <div className="flex gap-2">
              {showcaseScreens.slice(0, 4).map((screen) => (
                <span
                  key={screen.label}
                  className="rounded-full border border-border bg-muted/50 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground"
                >
                  {screen.label}
                </span>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function InfrastructureSection() {
  return (
    <section className="landing-section">
      <div className="mx-auto max-w-7xl px-6">
        <Reveal className="mx-auto max-w-3xl text-center">
          <BlynkSectionTitle>
            Production-ready IoT infrastructure
            <span className="mt-4 inline-block">
              <span className="blynk-stat-pill text-[clamp(1.25rem,2vw,2rem)]">without rebuilding the cloud</span>
            </span>
          </BlynkSectionTitle>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <Link to="/register" className={buttonVariants({ size: "lg" })}>
              Start free
            </Link>
            <Link to="/contact" className={buttonVariants({ variant: "outline", size: "lg" })}>
              Contact sales
            </Link>
          </div>
        </Reveal>
        <RevealStagger className="mt-16 grid gap-4 sm:grid-cols-2">
          {infraBlocks.map((block) => (
            <RevealItem key={block.title}>
              <Link
                to={block.to}
                className="blynk-platform-card group block h-full p-8 sm:p-10"
              >
                <h3 className="text-lg font-bold uppercase tracking-tight transition-colors group-hover:text-primary">
                  {block.title}
                </h3>
                <p className="mt-3 max-w-md text-pretty text-sm leading-relaxed text-muted-foreground">
                  {block.body}
                </p>
                <span className="mt-6 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide">
                  Learn more <ArrowRight size={14} />
                </span>
              </Link>
            </RevealItem>
          ))}
        </RevealStagger>
      </div>
    </section>
  );
}

export function BigStatementSection() {
  return (
    <section className="blynk-big-type landing-section relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,hsl(var(--primary)/0.08),transparent_50%)]" />
      <Reveal className="relative mx-auto max-w-7xl px-6">
        <p className="blynk-big-type-text font-brand text-[clamp(1.75rem,3.5vw+0.5rem,3.75rem)] font-bold uppercase leading-[1.05] tracking-tight">
          We are reshaping how teams connect people to their products — from prototype to global
          deployments, with provisioning, visualization, and fleet management in one platform.
        </p>
      </Reveal>
    </section>
  );
}

export function LandingFinalCta() {
  return (
    <section className="relative overflow-hidden px-6 py-28 sm:py-32">
      <div className="blynk-footer-dark absolute inset-0" aria-hidden />
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,hsl(var(--primary)/0.15),transparent_60%)]" />
      <Reveal className="relative mx-auto max-w-3xl text-center">
        <h2 className="font-brand text-[clamp(2.5rem,6vw,4.5rem)] font-bold uppercase leading-none tracking-tight text-white">
          Ready to launch?
        </h2>
        <p className="mx-auto mt-6 max-w-lg text-pretty text-base leading-relaxed text-white/60">
          Start free, invite your team, and connect your first device in minutes. Upgrade when your
          fleet grows.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/register" className={cn(buttonVariants({ size: "lg" }), "min-w-[220px]")}>
            Sign up free
            <ArrowRight size={18} weight="bold" />
          </Link>
          <Link
            to="/pricing"
            className={buttonVariants({
              variant: "outline",
              size: "lg",
              className:
                "min-w-[220px] border-white/20 bg-transparent text-white hover:bg-white/10 hover:text-white",
            })}
          >
            View pricing
          </Link>
        </div>
      </Reveal>
    </section>
  );
}
