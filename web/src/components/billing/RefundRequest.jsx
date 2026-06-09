import { useState } from "react";
import { toast } from "sonner";
import { ArrowCounterClockwise, CircleNotch } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { requestRefund } from "@/lib/billingApi";
import { extractApiError } from "@/lib/authApi";

// Refund request (Task 15.5, Req 17.5, 17.7). Submits POST /billing/refund for
// a payment/subscription. The backend enforces the 14-day money-back window:
// requests within 14 days of purchase are processed through Razorpay, and
// requests after the window are rejected — this UI surfaces whichever outcome
// the API returns rather than re-implementing the window client-side.

export default function RefundRequest() {
  const [paymentId, setPaymentId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    const id = paymentId.trim();
    if (!id) {
      toast.error("Enter the payment or subscription ID to refund.");
      return;
    }
    setSubmitting(true);
    try {
      await requestRefund({ paymentId: id });
      toast.success("Refund requested", {
        description: "Your refund is being processed through Razorpay.",
      });
      setPaymentId("");
    } catch (err) {
      const { code, message } = extractApiError(err);
      // The backend rejects requests past the 14-day window (Req 17.7).
      const description =
        code === "refund_window_elapsed"
          ? "The 14-day money-back window for this purchase has elapsed."
          : message;
      toast.error("Refund not processed", { description });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ArrowCounterClockwise size={20} className="text-primary" />
          <CardTitle className="text-xl">Request a refund</CardTitle>
        </div>
        <CardDescription>
          Refunds are available within 14 days of purchase under our money-back guarantee.
        </CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit}>
        <CardContent>
          <div className="space-y-1.5">
            <Label htmlFor="refund-payment-id">Payment or subscription ID</Label>
            <Input
              id="refund-payment-id"
              value={paymentId}
              onChange={(e) => setPaymentId(e.target.value)}
              placeholder="e.g. sub_… or the payment ID from your receipt"
              autoComplete="off"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button type="submit" variant="outline" disabled={submitting}>
            {submitting ? (
              <>
                <CircleNotch size={16} className="animate-spin" />
                Submitting…
              </>
            ) : (
              "Request refund"
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
