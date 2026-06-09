import { useState } from "react";
import { toast } from "sonner";
import { Bank, CircleNotch } from "@phosphor-icons/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { requestPayout } from "@/lib/partnerApi";
import { extractApiError } from "@/lib/authApi";

// Payout request form (Task 16.6, Req 18.4, 18.5). Submits POST /partner/payouts
// for an amount + optional destination. The backend enforces the balance check
// (Req 18.6): requests within the available balance are persisted PENDING for
// Super_Admin approval, and requests exceeding it are rejected
// (insufficient_balance) — this UI surfaces whichever outcome the API returns
// rather than re-checking the balance client-side.

export default function PayoutRequestForm({ balance, onRequested }) {
  const [amount, setAmount] = useState("");
  const [destination, setDestination] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    const numeric = Number(amount);
    if (!amount.trim() || Number.isNaN(numeric) || numeric <= 0) {
      toast.error("Enter a payout amount greater than zero.");
      return;
    }
    setSubmitting(true);
    try {
      const payout = await requestPayout({
        amount: numeric,
        destination: destination.trim() || undefined,
      });
      toast.success("Payout requested", {
        description: "Your request is pending Super Admin approval.",
      });
      setAmount("");
      setDestination("");
      onRequested?.(payout);
    } catch (err) {
      const { code, message } = extractApiError(err);
      // The backend rejects amounts over the available balance (Req 18.6).
      const description =
        code === "insufficient_balance"
          ? "The amount exceeds your available wallet balance."
          : message;
      toast.error("Payout not requested", { description });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Bank size={20} className="text-primary" />
          <CardTitle className="text-xl">Request a payout</CardTitle>
        </div>
        <CardDescription>
          Withdraw your commission balance to your bank or UPI account. Payouts
          are reviewed before they are paid out.
        </CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="payout-amount">Amount (₹)</Label>
            <Input
              id="payout-amount"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="e.g. 500"
              autoComplete="off"
            />
            {balance != null ? (
              <p className="text-xs text-muted-foreground">
                Available balance: ₹{balance}
              </p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="payout-destination">Destination (optional)</Label>
            <Input
              id="payout-destination"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="e.g. upi:you@bank or your account reference"
              autoComplete="off"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={submitting}>
            {submitting ? (
              <>
                <CircleNotch size={16} className="animate-spin" />
                Submitting…
              </>
            ) : (
              "Request payout"
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
