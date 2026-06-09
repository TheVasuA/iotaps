import { useState } from "react";
import { toast } from "sonner";
import { Tag, Trash, Percent, UsersThree, Warning } from "@phosphor-icons/react";
import {
  getCoupons,
  createCoupon,
  deleteCoupon,
  setCommissionOverride,
  getReferrals,
} from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

// Super_Admin coupons / commission / referral panel (Task 20.7, Req 26.1, 26.2,
// 26.4). Manages discount coupons (create/list/delete), per-partner commission
// overrides (PATCH /admin/partners/{id}/commission), and surfaces referral
// tracking with fraud flags (GET /admin/referrals).

function CouponsSection() {
  const { data, status, error, reload } = useAdminData(getCoupons);
  const coupons = data ?? [];

  const [code, setCode] = useState("");
  const [discountType, setDiscountType] = useState("percent");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const onCreate = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createCoupon({
        code: code.trim(),
        discountType,
        value: Number(value),
      });
      toast.success("Coupon created");
      setCode("");
      setValue("");
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id) => {
    try {
      await deleteCoupon(id);
      toast.success("Coupon deleted");
      reload();
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Tag size={20} className="text-primary" />
          Coupons
        </CardTitle>
        <CardDescription>Create and manage discount coupons (Req 26).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={onCreate}>
          <div className="space-y-1.5">
            <Label htmlFor="coupon-code">Code</Label>
            <Input
              id="coupon-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="SAVE20"
              required
            />
          </div>
          <div className="w-36 space-y-1.5">
            <Label htmlFor="coupon-type">Type</Label>
            <select
              id="coupon-type"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={discountType}
              onChange={(e) => setDiscountType(e.target.value)}
            >
              <option value="percent">Percent</option>
              <option value="fixed">Fixed</option>
            </select>
          </div>
          <div className="w-28 space-y-1.5">
            <Label htmlFor="coupon-value">Value</Label>
            <Input
              id="coupon-value"
              type="number"
              min={0}
              step="0.01"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            />
          </div>
          <Button type="submit" disabled={busy || !code.trim() || value === ""}>
            Create
          </Button>
        </form>

        <AdminPanel status={status} error={error}>
          {coupons.length === 0 ? (
            <p className="text-sm text-muted-foreground">No coupons yet.</p>
          ) : (
            <ul className="space-y-2">
              {coupons.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-2"
                >
                  <div className="flex items-center gap-3">
                    <code className="font-mono text-sm text-foreground">{c.code}</code>
                    <Badge variant={c.active ? "success" : "muted"}>
                      {c.active ? "active" : "inactive"}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {c.discount_type === "percent" ? `${c.value}%` : `₹${c.value}`}
                      {" · "}
                      {c.redemptions}
                      {c.max_redemptions != null ? `/${c.max_redemptions}` : ""} used
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onDelete(c.id)}
                    aria-label={`Delete coupon ${c.code}`}
                  >
                    <Trash size={16} />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

function CommissionSection() {
  const [orgId, setOrgId] = useState("");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (clear) => {
    setBusy(true);
    try {
      const result = await setCommissionOverride(
        orgId.trim(),
        clear ? null : Number(rate)
      );
      toast.success(
        result.commission_rate_override == null
          ? "Commission override cleared"
          : `Commission override set to ₹${result.commission_rate_override}`
      );
      if (clear) setRate("");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Percent size={20} className="text-primary" />
          Partner commission override
        </CardTitle>
        <CardDescription>
          Set a per-partner commission rate (0 is valid) or clear it back to the
          platform default (Req 26.1, 26.2).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit(false);
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="commission-org">Partner organization ID</Label>
            <Input
              id="commission-org"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              placeholder="org uuid"
              required
            />
          </div>
          <div className="w-32 space-y-1.5">
            <Label htmlFor="commission-rate">Rate (₹)</Label>
            <Input
              id="commission-rate"
              type="number"
              min={0}
              step="0.01"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy || !orgId.trim() || rate === ""}>
            Set
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy || !orgId.trim()}
            onClick={() => submit(true)}
          >
            Clear
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ReferralsSection() {
  const { data, status, error } = useAdminData(getReferrals);
  const referrals = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <UsersThree size={20} className="text-primary" />
          Referral tracking
        </CardTitle>
        <CardDescription>
          Referral records with fraud flags (Req 26.4).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AdminPanel status={status} error={error}>
          {referrals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No referral records.</p>
          ) : (
            <ul className="space-y-2">
              {referrals.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-card px-4 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-foreground">
                      {r.referred_gmail || r.referred_user_id || "Pending"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Referrer {r.referrer_user_id} · {r.status}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {r.fraud ? (
                      <Badge variant="warning">
                        <Warning size={12} /> fraud
                      </Badge>
                    ) : (
                      <Badge variant="success">clean</Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

export default function CouponsPanel() {
  return (
    <section className="space-y-6">
      <CouponsSection />
      <CommissionSection />
      <ReferralsSection />
    </section>
  );
}
