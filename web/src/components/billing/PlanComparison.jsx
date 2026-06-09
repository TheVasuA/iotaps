import { Check, Minus } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Plan comparison (Task 15.5, Req 17.1). Renders the Free and Pro plans side by
// side from GET /billing/plans so the entitlements shown always match what the
// backend enforces. `None` numeric limits denote "unlimited" (Pro).

function limitLabel(value, { suffix = "", unlimitedWhenNull = true } = {}) {
  if (value === null || value === undefined) {
    return unlimitedWhenNull ? "Unlimited" : "—";
  }
  return `${value.toLocaleString()}${suffix}`;
}

function FeatureRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

function BoolRow({ label, enabled }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {enabled ? (
        <Check size={18} className="text-emerald-500" aria-label="Included" />
      ) : (
        <Minus size={18} className="text-muted-foreground" aria-label="Not included" />
      )}
    </div>
  );
}

export default function PlanComparison({ plans, fromPriceMonthly }) {
  const free = plans?.free;
  const pro = plans?.pro;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-xl">Free</CardTitle>
            <Badge variant="muted">₹0</Badge>
          </div>
          <CardDescription>For students and small experiments.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <FeatureRow label="Devices" value={limitLabel(free?.max_devices, { unlimitedWhenNull: false })} />
          <FeatureRow
            label="Messages / month"
            value={limitLabel(free?.max_messages_per_month, { unlimitedWhenNull: false })}
          />
          <FeatureRow label="Data retention" value={limitLabel(free?.retention_days, { suffix: " days" })} />
          <FeatureRow label="Sensors / device" value={limitLabel(free?.max_sensors, { unlimitedWhenNull: false })} />
          <FeatureRow label="Active rules" value={limitLabel(free?.max_rules, { unlimitedWhenNull: false })} />
          <BoolRow label="Full device control" enabled={!!free?.full_control} />
        </CardContent>
      </Card>

      <Card className="border-primary/50 ring-1 ring-primary/30">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-xl text-primary">Pro</CardTitle>
            <Badge variant="default">
              {fromPriceMonthly != null ? `from ₹${fromPriceMonthly}/device/mo` : "Pro"}
            </Badge>
          </div>
          <CardDescription>Volume pricing, full control, and long retention.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <FeatureRow label="Devices" value={limitLabel(pro?.max_devices)} />
          <FeatureRow label="Messages / month" value={limitLabel(pro?.max_messages_per_month)} />
          <FeatureRow label="Data retention" value={limitLabel(pro?.retention_days, { suffix: " days" })} />
          <FeatureRow label="Sensors / device" value={limitLabel(pro?.max_sensors)} />
          <FeatureRow label="Active rules" value={limitLabel(pro?.max_rules)} />
          <BoolRow label="Full device control" enabled={!!pro?.full_control} />
          {pro?.annual_unit_price != null ? (
            <FeatureRow label="Annual price" value={`₹${pro.annual_unit_price}/device/yr`} />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
