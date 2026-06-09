import { Link } from "react-router-dom";
import { Check } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { PublicPage, PageHeader } from "@/components/public/PublicPage";
import {
  PRICING_TIERS,
  ANNUAL_UNIT_PRICE,
  unitPriceMonthly,
} from "@/lib/pricing";

// Public pricing page (Task 21.1, Req 31.1-31.3). Presents three columns -
// Free, Pro, and the Referral program (Req 31.2). The Referral column shows the
// exact required copy "6 friends = 3 devices free 3 months" and
// "ALL PRO FEATURES INCLUDED" (Req 31.3).
//
// Pro pricing is sourced from the shared volume-discount mirror in
// src/lib/pricing.js so the marketing page matches what billing charges.

// Lowest advertised monthly per-device price (the open-ended top tier).
const fromPriceMonthly = unitPriceMonthly(
  PRICING_TIERS[PRICING_TIERS.length - 1].minDevices
);

const freeFeatures = [
  "2 devices",
  "20,000 messages / month",
  "7 days data retention",
  "10 sensors",
  "2 active rules",
  "View-only device access",
];

const proFeatures = [
  "Unlimited devices",
  "Unlimited messages",
  "3 months raw + 1 year history",
  "20 sensors per device",
  "Unlimited rules",
  "Full device control & OTA",
  "Rule engine & notifications",
];

const referralRewards = [
  "1 referral → 1 device free for 1 month",
  "2 referrals → 2 devices free for 1 month",
  "6 friends = 3 devices free 3 months",
];

function FeatureList({ items }) {
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2 text-sm text-foreground">
          <Check size={18} className="mt-0.5 shrink-0 text-emerald-500" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default function PricingPage() {
  return (
    <PublicPage className="max-w-6xl">
      <PageHeader
        title="Pricing"
        subtitle="Start free, scale to Pro with volume discounts, or earn Pro for free by referring friends."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Free column (Req 31.2) */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xl">Free</CardTitle>
              <Badge variant="muted">₹0</Badge>
            </div>
            <CardDescription>For students and small experiments.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1">
            <FeatureList items={freeFeatures} />
          </CardContent>
          <CardFooter>
            <Link to="/register" className={buttonVariants({ variant: "outline", className: "w-full" })}>
              Get started
            </Link>
          </CardFooter>
        </Card>

        {/* Pro column (Req 31.2) */}
        <Card className="flex flex-col border-primary/50 ring-1 ring-primary/30">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xl text-primary">Pro</CardTitle>
              <Badge variant="default">Most popular</Badge>
            </div>
            <CardDescription>
              From ₹{fromPriceMonthly}/device/mo · ₹{ANNUAL_UNIT_PRICE}/device/yr
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 space-y-4">
            <FeatureList items={proFeatures} />
            <div className="rounded-md border border-border bg-muted/40 p-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                Volume pricing (per device / month)
              </p>
              <ul className="space-y-0.5 text-xs text-foreground">
                {PRICING_TIERS.map((tier) => (
                  <li key={tier.minDevices} className="flex justify-between gap-2">
                    <span>
                      {tier.maxDevices
                        ? `${tier.minDevices}–${tier.maxDevices} devices`
                        : `${tier.minDevices}+ devices`}
                    </span>
                    <span className="font-medium">₹{tier.unitPriceMonthly}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
          <CardFooter>
            <Link to="/register" className={buttonVariants({ className: "w-full" })}>
              Upgrade to Pro
            </Link>
          </CardFooter>
        </Card>

        {/* Referral column (Req 31.2, 31.3) */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xl">Referral</CardTitle>
              <Badge variant="success">Free Pro</Badge>
            </div>
            {/* Required copy (Req 31.3) */}
            <CardDescription className="font-semibold text-foreground">
              6 friends = 3 devices free 3 months
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 space-y-4">
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
              ALL PRO FEATURES INCLUDED
            </p>
            <FeatureList items={referralRewards} />
            <p className="text-xs text-muted-foreground">
              Rewards are capped at 3 devices for 3 months, granted with full Pro
              features and no payment required from your friends.
            </p>
          </CardContent>
          <CardFooter>
            <Link to="/register" className={buttonVariants({ variant: "outline", className: "w-full" })}>
              Start referring
            </Link>
          </CardFooter>
        </Card>
      </div>
    </PublicPage>
  );
}
