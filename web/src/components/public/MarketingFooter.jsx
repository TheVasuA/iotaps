import { Link } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import BrandMark from "@/components/BrandMark";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

const footerColumns = [
  {
    title: "Platform",
    links: [
      { to: "/platform", label: "Overview" },
      { to: "/pricing", label: "Pricing" },
      { to: "/status", label: "System status" },
      { to: "/changelog", label: "Changelog" },
      { to: "/register", label: "Sign up free" },
    ],
  },
  {
    title: "Solutions",
    links: [
      { to: "/solutions/industrial-iot", label: "Industrial IoT" },
      { to: "/solutions/smart-agriculture", label: "Smart agriculture" },
      { to: "/solutions/energy-hvac", label: "Energy & HVAC" },
      { to: "/enterprise", label: "Enterprise" },
      { to: "/blynk-alternative", label: "Migrating to IoTAPS" },
      { to: "/faq", label: "FAQ" },
    ],
  },
  {
    title: "Developers",
    links: [
      { to: "/docs", label: "Documentation" },
      { to: "/developers/mqtt-devices", label: "MQTT & devices" },
      { to: "/developers/dashboards-api", label: "Dashboards API" },
      { to: "/changelog", label: "Release notes" },
    ],
  },
  {
    title: "Company",
    links: [
      { to: "/about", label: "About us" },
      { to: "/contact", label: "Contact" },
      { to: "/partners", label: "Partners" },
    ],
  },
  {
    title: "Legal",
    links: [
      { to: "/terms", label: "Terms of service" },
      { to: "/privacy", label: "Privacy policy" },
      { to: "/refund-policy", label: "Refund policy" },
      { to: "/security", label: "Security contact" },
    ],
  },
];

export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="marketing-footer">
      <div className="marketing-footer-cta border-b border-white/10">
        <div className="mx-auto flex max-w-[1440px] flex-col items-start justify-between gap-6 px-6 py-10 sm:flex-row sm:items-center sm:px-8">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary">Get started</p>
            <p className="mt-2 font-brand text-xl font-bold text-white sm:text-2xl">
              Connect your first device today
            </p>
            <p className="mt-2 max-w-md text-sm text-white/55">
              Free tier, MQTT-native provisioning, and a console your team can use in minutes.
            </p>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <Link to="/register" className={cn(buttonVariants({ size: "lg" }), "w-full sm:w-auto")}>
              Create account
              <ArrowRight size={18} weight="bold" />
            </Link>
            <Link
              to="/contact"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "w-full border-white/25 bg-transparent text-white hover:bg-white/10 hover:text-white sm:w-auto"
              )}
            >
              Talk to sales
            </Link>
          </div>
        </div>
      </div>

      <div className="marketing-footer-main">
        <div className="mx-auto grid max-w-[1440px] gap-10 px-6 py-14 sm:grid-cols-2 lg:grid-cols-12 lg:gap-8 lg:px-8">
          <div className="lg:col-span-4">
            <Link to="/" className="inline-flex items-center gap-2.5">
              <BrandMark size={36} className="rounded-none" />
              <span className="font-brand text-xl font-bold text-white">iotaps</span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-white/55">
              IoT Automation Platform Services — dashboards, devices, rule chains, and billing for
              teams shipping connected products.
            </p>
            <p className="mt-4 text-sm text-white/60">
              <a href="mailto:support@iotaps.com" className="text-white/70 transition hover:text-primary">
                support@iotaps.com
              </a>
            </p>
            {/* No social icon row: there are no verified IoTAPS profiles to link
                to, and pointing at the bare platform homepages reads as though
                those accounts exist. Add icons back only with real profile URLs. */}
          </div>

          {footerColumns.map((col) => (
            <div key={col.title} className="lg:col-span-2">
              <h2 className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/90">{col.title}</h2>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      to={link.to}
                      className="text-sm text-white/50 transition-colors hover:text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div className="marketing-footer-bottom border-t border-white/10">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-6 py-6 text-xs text-white/60 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>© {year} IoTAPS. All rights reserved.</p>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Link to="/status" className="hover:text-white/75">
              Status
            </Link>
            <Link to="/privacy" className="hover:text-white/75">
              Privacy
            </Link>
            <Link to="/terms" className="hover:text-white/75">
              Terms
            </Link>
            <Link to="/refund-policy" className="hover:text-white/75">
              Refunds
            </Link>
            <span className="hidden h-3 w-px bg-white/20 sm:inline" aria-hidden />
            <span className="text-white/55">Region: Global · EN</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
