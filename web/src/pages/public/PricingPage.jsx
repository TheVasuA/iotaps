import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, Gift, Lightning, Sparkle } from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { MarketingShell } from "@/components/public/PublicPage";
import { MarketingRelatedLinks } from "@/pages/public/marketing/createMarketingPage";
import { getPublicPlans } from "@/lib/publicApi";
import { marketingImages } from "@/lib/marketingImages";
import { cn } from "@/lib/utils";
import {
  PRICING_TIERS,
  ANNUAL_UNIT_PRICE,
  CYCLE_MONTHLY,
  CYCLE_YEARLY,
} from "@/lib/pricing";

// Prices and volume tiers are fetched from GET /billing/plans (a pure public
// pricing read) so the page stays in lockstep with what checkout charges; the
// @/lib/pricing constants are the fallback so a failed fetch never blanks the
// page. Checkout quote math itself stays in @/lib/pricing.

const freeFeatures = [
  "2 devices included",
  "20,000 messages / month",
  "7 days data retention",
  "10 sensors per device",
  "2 active rule chains",
  "View-only device access",
];

const proFeatures = [
  "Unlimited devices",
  "Unlimited messages",
  "3 months raw + 1 year history",
  "20 sensors per device",
  "Unlimited rule chains",
  "Full device control & OTA",
  "Notifications & webhooks",
];

const referralRewards = [
  "1 referral → 1 device free for 1 month",
  "2 referrals → 2 devices free for 1 month",
  "6 friends = 3 devices free 3 months",
];

const compareRows = [
  { label: "Devices", free: "2", pro: "Unlimited" },
  { label: "Messages / month", free: "20,000", pro: "Unlimited" },
  { label: "Data retention", free: "7 days", pro: "Extended" },
  { label: "Rule chains", free: "2", pro: "Unlimited" },
  { label: "Device control", free: "View only", pro: "Full + OTA" },
];

function PlanFeatureList({ items }) {
  return (
    <ul className="mt-6 space-y-3">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2.5 text-sm text-foreground">
          <Check size={18} weight="bold" className="mt-0.5 shrink-0 text-primary" aria-hidden />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function BillingToggle({ cycle, onChange }) {
  return (
    <div className="pricing-billing-toggle inline-flex rounded-lg border border-border bg-muted/50 p-1">
      <button
        type="button"
        className={cn(
          "rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide transition",
          cycle === CYCLE_MONTHLY ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
        )}
        onClick={() => onChange(CYCLE_MONTHLY)}
      >
        Monthly
      </button>
      <button
        type="button"
        className={cn(
          "rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide transition",
          cycle === CYCLE_YEARLY ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
        )}
        onClick={() => onChange(CYCLE_YEARLY)}
      >
        Annual
      </button>
    </div>
  );
}

export default function PricingPage() {
  const [cycle, setCycle] = useState(CYCLE_MONTHLY);
  const [pricing, setPricing] = useState({
    annualUnitPrice: ANNUAL_UNIT_PRICE,
    tiers: PRICING_TIERS,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const plans = await getPublicPlans();
        if (!cancelled && plans) setPricing(plans);
      } catch {
        // Keep the bundled @/lib/pricing mirror as the fallback.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const { annualUnitPrice, tiers } = pricing;
  // Headline rate is the ENTRY tier (1-10 devices), matching the meta
  // description. The volume ladder down to the 201+ band is in the table
  // below; advertising the floor as "from" would imply a fleet of one can
  // start at that price.
  const entryPriceMonthly = tiers[0].unitPriceMonthly;
  const floorPriceMonthly = tiers[tiers.length - 1].unitPriceMonthly;
  const proPriceLabel =
    cycle === CYCLE_YEARLY
      ? `₹${annualUnitPrice}`
      : `from ₹${entryPriceMonthly}`;
  const proPriceSuffix = cycle === CYCLE_YEARLY ? "per device / year" : "per device / mo";

  return (
    <MarketingShell
      eyebrow="Pricing"
      title="Simple plans for every fleet size"
      subtitle="Start on Free, grow into Pro with volume discounts, or unlock Pro through referrals — same console, same purple-accent experience."
      image={marketingImages.analyticsDashboard}
      imageAlt="IoT platform analytics and fleet scaling"
      metaTitle="Pricing — Free & Pro plans"
      metaDescription="Free plan with 2 devices and 20,000 messages/month, or Pro from ₹99/device/mo with volume discounts down to ₹59. No credit card to start."
      wide
      showCta={false}
    >
      <MarketingRelatedLinks
        links={[
          { to: "/platform", label: "Platform overview" },
          { to: "/faq", label: "Pricing FAQ" },
          { to: "/partners", label: "Partners" },
          { to: "/register", label: "Sign up free" },
        ]}
      />

      <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
        <p className="max-w-lg text-sm text-muted-foreground">
          Pro pricing uses fleet-wide volume tiers. Toggle billing cycle to see monthly vs annual unit rates.
        </p>
        <BillingToggle cycle={cycle} onChange={setCycle} />
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-3 lg:items-stretch">
        <article className="pricing-plan-card flex flex-col">
          <div className="pricing-plan-accent bg-muted-foreground/30" />
          <div className="flex flex-1 flex-col p-6 sm:p-8">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Starter</p>
            <h2 className="mt-2 font-brand text-2xl font-bold uppercase tracking-tight">Free</h2>
            <p className="mt-2 text-sm text-muted-foreground">For students and small experiments.</p>
            <p className="mt-6 flex items-baseline gap-1">
              <span className="font-brand text-4xl font-bold tracking-tight">₹0</span>
            </p>
            <PlanFeatureList items={freeFeatures} />
            <Link
              to="/register"
              className={cn(buttonVariants({ variant: "outline" }), "mt-auto w-full pt-8")}
            >
              Get started
            </Link>
          </div>
        </article>

        <article className="pricing-plan-card pricing-plan-card-featured relative flex flex-col lg:-mt-2 lg:mb-2">
          <div className="pricing-plan-accent bg-primary" />
          <span className="absolute right-6 top-6 inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-primary-foreground">
            <Sparkle size={12} weight="fill" />
            Most popular
          </span>
          <div className="flex flex-1 flex-col p-6 sm:p-8">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">Scale</p>
            <h2 className="mt-2 font-brand text-2xl font-bold uppercase tracking-tight text-primary">Pro</h2>
            <p className="mt-2 text-sm text-muted-foreground">Volume discounts as your fleet grows.</p>
            <p className="mt-6 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="font-brand text-4xl font-bold tracking-tight">{proPriceLabel}</span>
              <span className="text-sm text-muted-foreground">{proPriceSuffix}</span>
            </p>
            {cycle === CYCLE_MONTHLY ? (
              <>
                <p className="mt-1 text-xs text-muted-foreground">
                  Volume discounts down to ₹{floorPriceMonthly}/device/mo at 201+ devices
                </p>
                <p className="mt-1 text-xs text-muted-foreground">or ₹{annualUnitPrice}/device/yr billed annually</p>
              </>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">≈ ₹{Math.round(annualUnitPrice / 12)}/device/mo equivalent</p>
            )}
            <PlanFeatureList items={proFeatures} />
            <Link to="/register" className={cn(buttonVariants(), "mt-auto w-full pt-8")}>
              Upgrade to Pro
              <ArrowRight size={16} weight="bold" />
            </Link>
          </div>
        </article>

        <article className="pricing-plan-card flex flex-col">
          <div className="pricing-plan-accent bg-emerald-500/80" />
          <div className="flex flex-1 flex-col p-6 sm:p-8">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Community</p>
            <h2 className="mt-2 flex items-center gap-2 font-brand text-2xl font-bold uppercase tracking-tight">
              <Gift size={26} weight="duotone" className="text-primary" />
              Referral
            </h2>
            <p className="mt-3 text-sm font-semibold text-foreground">6 friends = 3 devices free 3 months</p>
            <p className="mt-2 text-xs font-bold uppercase tracking-wide text-primary">
              ALL PRO FEATURES INCLUDED
            </p>
            <PlanFeatureList items={referralRewards} />
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
              Rewards cap at 3 devices for 3 months with full Pro entitlements. Friends are not charged.
            </p>
            <Link
              to="/register"
              className={cn(buttonVariants({ variant: "outline" }), "mt-auto w-full pt-6")}
            >
              Start referring
            </Link>
          </div>
        </article>
      </div>

      <section className="pricing-volume-band mt-14 overflow-hidden rounded-2xl border border-border" aria-labelledby="volume-heading">
        <div className="border-b border-white/10 bg-[#0a0a0a] px-6 py-5 sm:px-8">
          <div className="flex flex-wrap items-center gap-3">
            <Lightning size={22} weight="fill" className="text-primary" />
            <div>
              <h2 id="volume-heading" className="font-brand text-lg font-bold uppercase tracking-tight text-white">
                Volume pricing
              </h2>
              <p className="text-sm text-white/55">Monthly per-device rate by fleet band (whole purchase)</p>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto bg-[#111]">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-[10px] font-bold uppercase tracking-wider text-white/60">
                <th className="px-6 py-4 sm:px-8">Fleet size</th>
                <th className="px-6 py-4 sm:px-8">Price / device / month</th>
                <th className="hidden px-6 py-4 sm:table-cell sm:px-8">Annual equivalent</th>
              </tr>
            </thead>
            <tbody>
              {tiers.map((tier) => {
                const annualEquiv = tier.unitPriceMonthly * 12;
                const saves = annualEquiv - annualUnitPrice;
                return (
                  <tr key={tier.minDevices} className="border-b border-white/5 text-white/85 last:border-0">
                    <td className="px-6 py-4 font-medium sm:px-8">
                      {tier.maxDevices
                        ? `${tier.minDevices}–${tier.maxDevices} devices`
                        : `${tier.minDevices}+ devices`}
                    </td>
                    <td className="px-6 py-4 sm:px-8">
                      <span className="font-brand text-lg font-bold text-primary">₹{tier.unitPriceMonthly}</span>
                    </td>
                    <td className="hidden px-6 py-4 text-white/50 sm:table-cell sm:px-8">
                      ₹{annualUnitPrice}/yr fixed
                      {saves > 0 ? (
                        <span className="ml-2 text-xs text-primary">save vs ₹{annualEquiv}/yr at tier rate</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14" aria-labelledby="compare-heading">
        <h2 id="compare-heading" className="font-brand text-xl font-bold uppercase tracking-tight">
          Quick comparison
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">What changes when you move from Free to Pro.</p>
        <div className="mt-6 overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 text-left text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                <th className="px-5 py-3 sm:px-6">Feature</th>
                <th className="px-5 py-3 sm:px-6">Free</th>
                <th className="px-5 py-3 sm:px-6 text-primary">Pro</th>
              </tr>
            </thead>
            <tbody>
              {compareRows.map((row) => (
                <tr key={row.label} className="border-t border-border">
                  <td className="px-5 py-3.5 font-medium text-foreground sm:px-6">{row.label}</td>
                  <td className="px-5 py-3.5 text-muted-foreground sm:px-6">{row.free}</td>
                  <td className="px-5 py-3.5 font-semibold text-foreground sm:px-6">{row.pro}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14 rounded-2xl border border-primary/25 bg-primary/5 px-6 py-10 text-center sm:px-10">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-primary">Ready to deploy</p>
        <p className="mt-3 font-brand text-2xl font-bold uppercase tracking-tight">Start free — upgrade when you scale</p>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          No credit card for Free. Pro checkout via Razorpay when your fleet is ready.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/register" className={cn(buttonVariants({ size: "lg" }), "min-w-[200px]")}>
            Create account
            <ArrowRight size={18} weight="bold" />
          </Link>
          <Link to="/contact" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "min-w-[200px]")}>
            Contact sales
          </Link>
        </div>
      </section>
    </MarketingShell>
  );
}
