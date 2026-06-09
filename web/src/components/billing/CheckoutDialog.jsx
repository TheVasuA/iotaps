import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CircleNotch, ShieldCheck } from "@phosphor-icons/react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { subscribe } from "@/lib/billingApi";
import { extractApiError } from "@/lib/authApi";

// Checkout flow (Task 15.5, Req 17.1, 17.4). Confirms the purchase and creates
// a Razorpay order via POST /billing/subscribe (optionally with a coupon). The
// order is "created" here; the subscription is activated later when Razorpay
// confirms capture via the signed webhook (Req 17.2), so we surface the order
// summary and tell the customer payment is the next step.
//
// Razorpay Checkout.js is loaded by the host page in production; this dialog is
// resilient to its absence (local/dev) and falls back to showing the created
// order so the flow can be exercised without the external SDK.

export default function CheckoutDialog({ open, onClose, purchase, onSuccess }) {
  const [coupon, setCoupon] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [order, setOrder] = useState(null);

  // Reset transient state whenever the dialog is (re)opened for a purchase.
  useEffect(() => {
    if (open) {
      setCoupon("");
      setOrder(null);
      setSubmitting(false);
    }
  }, [open, purchase]);

  if (!purchase) return null;

  const onConfirm = async () => {
    setSubmitting(true);
    try {
      const result = await subscribe({
        deviceCount: purchase.deviceCount,
        billingCycle: purchase.billingCycle,
        deviceId: purchase.deviceId,
        coupon: coupon.trim() || undefined,
      });
      setOrder(result);
      onSuccess?.(result);
      toast.success("Order created", {
        description: `Razorpay order ${result.razorpay_order.id} for ₹${result.amount_due.toLocaleString()}.`,
      });
    } catch (err) {
      const { message } = extractApiError(err);
      toast.error("Could not start checkout", { description: message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Checkout"
      description="Review your Pro subscription and start payment."
    >
      <DialogBody className="space-y-4">
        <div className="rounded-md border border-border bg-muted/30 p-4 text-sm">
          <div className="flex justify-between py-1">
            <span className="text-muted-foreground">Plan</span>
            <span className="font-medium capitalize">Pro · {purchase.billingCycle}</span>
          </div>
          <div className="flex justify-between py-1">
            <span className="text-muted-foreground">Devices</span>
            <span className="font-medium">{purchase.deviceCount.toLocaleString()}</span>
          </div>
          {purchase.deviceId ? (
            <div className="flex justify-between py-1">
              <span className="text-muted-foreground">Scope</span>
              <span className="font-medium">Single device</span>
            </div>
          ) : null}
        </div>

        {order ? (
          <div className="space-y-3">
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
              <div className="flex justify-between py-1">
                <span className="text-muted-foreground">Order ID</span>
                <span className="font-mono text-xs">{order.razorpay_order.id}</span>
              </div>
              {order.coupon_applied ? (
                <div className="flex justify-between py-1">
                  <span className="text-muted-foreground">Coupon</span>
                  <span className="font-medium">{order.coupon_applied}</span>
                </div>
              ) : null}
              <div className="mt-1 flex items-baseline justify-between border-t border-border pt-2">
                <span className="font-medium">Amount due</span>
                <span className="text-xl font-semibold">₹{order.amount_due.toLocaleString()}</span>
              </div>
            </div>
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <ShieldCheck size={16} className="mt-0.5 shrink-0 text-emerald-500" />
              Complete payment in the Razorpay window. Your subscription activates once
              the payment is confirmed.
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="coupon">Coupon code (optional)</Label>
            <Input
              id="coupon"
              value={coupon}
              onChange={(e) => setCoupon(e.target.value)}
              placeholder="e.g. WELCOME10"
              autoComplete="off"
            />
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        {order ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="outline" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={onConfirm} disabled={submitting}>
              {submitting ? (
                <>
                  <CircleNotch size={16} className="animate-spin" />
                  Creating order…
                </>
              ) : (
                "Pay with Razorpay"
              )}
            </Button>
          </>
        )}
      </DialogFooter>
    </Dialog>
  );
}
