import { useMemo, useState } from "react";
import { Calculator } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CYCLE_MONTHLY,
  CYCLE_YEARLY,
  PRICING_TIERS,
  quote as computeQuote,
  unitPriceMonthly,
} from "@/lib/pricing";

// Quote calculator (Task 15.5, Req 16, 17.4). Uses the frontend pricing mirror
// (src/lib/pricing.js) for an instant, offline preview that matches the backend
// billing engine. `onCheckout` hands the resolved purchase up to the page so it
// can create the Razorpay order via POST /billing/subscribe.

const TIER_LABEL = (tier) =>
  tier.maxDevices === null
    ? `${tier.minDevices}+ devices`
    : `${tier.minDevices}\u2013${tier.maxDevices} devices`;

export default function QuoteCalculator({ onCheckout, submitting }) {
  const [deviceCount, setDeviceCount] = useState(1);
  const [billingCycle, setBillingCycle] = useState(CYCLE_MONTHLY);

  // Coerce the input to a valid integer >= 1 for the live preview.
  const count = Number.isInteger(deviceCount) && deviceCount >= 1 ? deviceCount : null;

  const preview = useMemo(() => {
    if (count === null) return null;
    return computeQuote(count, billingCycle);
  }, [count, billingCycle]);

  const monthlyRate = count !== null ? unitPriceMonthly(count) : null;

  const onCountChange = (e) => {
    const raw = parseInt(e.target.value, 10);
    setDeviceCount(Number.isNaN(raw) ? "" : raw);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Calculator size={20} className="text-primary" />
          <CardTitle className="text-xl">Quote calculator</CardTitle>
        </div>
        <CardDescription>
          Pro pricing scales with fleet size. Annual billing is a flat ₹948 per device.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="device-count">Number of devices</Label>
            <Input
              id="device-count"
              type="number"
              min={1}
              value={deviceCount}
              onChange={onCountChange}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="billing-cycle">Billing cycle</Label>
            <div className="flex gap-2" role="group" aria-label="Billing cycle">
              {[CYCLE_MONTHLY, CYCLE_YEARLY].map((cycle) => (
                <Button
                  key={cycle}
                  type="button"
                  variant={billingCycle === cycle ? "default" : "outline"}
                  className="flex-1 capitalize"
                  onClick={() => setBillingCycle(cycle)}
                  aria-pressed={billingCycle === cycle}
                >
                  {cycle}
                </Button>
              ))}
            </div>
          </div>
        </div>

        {/* Volume tier breakdown (Req 16.2-16.5). Highlights the active band. */}
        <div className="rounded-md border border-border">
          <div className="border-b border-border bg-muted/50 px-3 py-2 text-xs font-medium uppercase text-muted-foreground">
            Monthly volume tiers
          </div>
          <ul className="divide-y divide-border text-sm">
            {PRICING_TIERS.map((tier) => {
              const active =
                billingCycle === CYCLE_MONTHLY &&
                monthlyRate === tier.unitPriceMonthly &&
                count !== null &&
                count >= tier.minDevices &&
                (tier.maxDevices === null || count <= tier.maxDevices);
              return (
                <li
                  key={tier.minDevices}
                  className={cn(
                    "flex items-center justify-between px-3 py-2",
                    active && "bg-primary/10 font-medium text-primary"
                  )}
                >
                  <span>{TIER_LABEL(tier)}</span>
                  <span>₹{tier.unitPriceMonthly}/device/mo</span>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Live total (Req 16.6, 16.7). */}
        <div className="rounded-md border border-border bg-card p-4">
          {preview ? (
            <>
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  {preview.deviceCount.toLocaleString()} {preview.deviceCount === 1 ? "device" : "devices"}
                  {" \u00d7 "}
                  ₹{preview.unitPrice}/device/{billingCycle === CYCLE_YEARLY ? "yr" : "mo"}
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-sm font-medium text-foreground">Total</span>
                <span className="text-2xl font-semibold text-foreground">
                  ₹{preview.total.toLocaleString()}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">
                    /{billingCycle === CYCLE_YEARLY ? "year" : "month"}
                  </span>
                </span>
              </div>
            </>
          ) : (
            <p className="text-sm text-destructive">Enter a device count of 1 or more.</p>
          )}
        </div>
      </CardContent>
      <CardFooter>
        <Button
          className="w-full"
          disabled={!preview || submitting}
          onClick={() => preview && onCheckout({ deviceCount: count, billingCycle })}
        >
          {submitting ? "Starting checkout…" : "Continue to checkout"}
        </Button>
      </CardFooter>
    </Card>
  );
}
