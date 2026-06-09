import { useCallback, useEffect, useState } from "react";
import { CircleNotch, Wallet, Coins } from "@phosphor-icons/react";
import { getWallet } from "@/lib/partnerApi";
import { extractApiError } from "@/lib/authApi";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import PayoutRequestForm from "@/components/partner/PayoutRequestForm";

// Partner wallet page (Task 16.6, Req 18.4, 18.5). Surfaces the caller's
// partner state from GET /partner/wallet:
//   - the current commission balance
//   - the commission history that built up that balance
//   - a payout request form (POST /partner/payouts) to withdraw the balance
//
// After a payout is requested the wallet is reloaded so the balance and history
// reflect the server's latest state.

function formatMonth(period) {
  if (!period) return null;
  // period_month is a YYYY-MM string; render it as e.g. "Jan 2025".
  const d = new Date(`${period}-01T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return period;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

function WalletBalance({ balance }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Wallet balance</CardTitle>
        <CardDescription>
          Your available commission balance, ready to withdraw.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3">
          <Wallet size={32} className="text-primary" />
          <span className="text-4xl font-semibold text-foreground">
            ₹{balance}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function CommissionHistory({ commissions }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Commission history</CardTitle>
        <CardDescription>
          Commissions credited to your wallet.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {commissions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No commissions yet. Commissions appear here as your referred
            customers are billed.
          </p>
        ) : (
          <ul className="space-y-3">
            {commissions.map((commission) => {
              const month = formatMonth(commission.period_month);
              return (
                <li
                  key={commission.id}
                  className="flex items-start gap-3 rounded-md border border-border bg-card p-4"
                >
                  <Coins size={24} className="mt-0.5 text-primary" />
                  <div className="flex-1 space-y-1">
                    <p className="font-medium text-foreground">
                      ₹{commission.amount}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {month ? `For ${month}.` : ""}
                      {commission.device_id
                        ? ` Device ${commission.device_id}.`
                        : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function WalletPage() {
  const [wallet, setWallet] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | succeeded | failed
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    try {
      const data = await getWallet();
      if (!signal?.cancelled) {
        setWallet(data);
        setStatus("succeeded");
      }
    } catch (err) {
      if (!signal?.cancelled) {
        setError(extractApiError(err).message);
        setStatus("failed");
      }
    }
  }, []);

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load]);

  const onRequested = () => {
    // Reload the wallet so the balance/history reflect the new pending payout.
    load();
  };

  return (
    <section className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-primary">Partner wallet</h1>
        <p className="text-sm text-muted-foreground">
          Track your commission earnings and request payouts.
        </p>
      </header>

      {status === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : status === "failed" ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-destructive">
          {error || "Failed to load wallet"}
        </div>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <WalletBalance balance={wallet.balance} />
            <CommissionHistory commissions={wallet.commissions ?? []} />
          </div>
          <PayoutRequestForm balance={wallet.balance} onRequested={onRequested} />
        </>
      )}
    </section>
  );
}
