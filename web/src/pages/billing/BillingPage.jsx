import { useEffect, useState } from "react";
import { CircleNotch } from "@phosphor-icons/react";
import { getPlans } from "@/lib/billingApi";
import { extractApiError } from "@/lib/authApi";
import PlanComparison from "@/components/billing/PlanComparison";
import QuoteCalculator from "@/components/billing/QuoteCalculator";
import CheckoutDialog from "@/components/billing/CheckoutDialog";
import RefundRequest from "@/components/billing/RefundRequest";

// Billing & subscription page (Task 15.5, Req 17.1, 17.4, 17.5). Brings together
// the four pieces of the billing surface:
//   - Plan comparison      (Free vs Pro, from GET /billing/plans)
//   - Quote calculator     (volume pricing preview via the pricing mirror)
//   - Checkout flow        (POST /billing/subscribe -> Razorpay order)
//   - Refund request       (POST /billing/refund, 14-day money-back window)

export default function BillingPage() {
  const [plans, setPlans] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | succeeded | failed
  const [error, setError] = useState(null);

  const [purchase, setPurchase] = useState(null);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getPlans();
        if (!cancelled) {
          setPlans(data);
          setStatus("succeeded");
        }
      } catch (err) {
        if (!cancelled) {
          setError(extractApiError(err).message);
          setStatus("failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const fromPriceMonthly = plans?.pricing_tiers?.length
    ? Math.min(...plans.pricing_tiers.map((t) => t.unit_price_monthly))
    : plans?.pro?.unit_price_monthly ?? null;

  const onCheckout = (next) => {
    setPurchase(next);
    setCheckoutOpen(true);
  };

  return (
    <section className="mx-auto max-w-5xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-primary">Billing &amp; subscription</h1>
        <p className="text-sm text-muted-foreground">
          Compare plans, size your fleet, and manage your Pro subscription.
        </p>
      </header>

      {status === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : status === "failed" ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-destructive">
          {error || "Failed to load plans"}
        </div>
      ) : (
        <>
          <PlanComparison plans={plans} fromPriceMonthly={fromPriceMonthly} />

          <div className="grid gap-6 lg:grid-cols-2">
            <QuoteCalculator onCheckout={onCheckout} />
            <RefundRequest />
          </div>
        </>
      )}

      <CheckoutDialog
        open={checkoutOpen}
        onClose={() => setCheckoutOpen(false)}
        purchase={purchase}
      />
    </section>
  );
}
