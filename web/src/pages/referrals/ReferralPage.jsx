import { useEffect, useState } from "react";
import { CircleNotch, Copy, Check, Gift, UsersThree } from "@phosphor-icons/react";
import { toast } from "sonner";
import { getReferralSummary } from "@/lib/referralsApi";
import { extractApiError } from "@/lib/authApi";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// Referral page (Task 17.3, Req 19.1, 19.2). Surfaces the caller's referral
// state from GET /referrals:
//   - the shareable referral code, with copy-to-clipboard
//   - the confirmed referral count
//   - the granted referral rewards (free Pro device-months)

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function ReferralCode({ code }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      toast.success("Referral code copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy to clipboard");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Your referral code</CardTitle>
        <CardDescription>
          Share this code with friends. When they sign up with it, you earn free
          Pro device-months.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3">
          <code className="flex-1 rounded-md border border-border bg-muted px-4 py-3 font-mono text-lg tracking-widest text-foreground">
            {code}
          </code>
          <Button
            type="button"
            variant="outline"
            onClick={onCopy}
            aria-label="Copy referral code"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
            <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReferralCount({ count }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Confirmed referrals</CardTitle>
        <CardDescription>
          Friends who have signed up with your code.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3">
          <UsersThree size={32} className="text-primary" />
          <span className="text-4xl font-semibold text-foreground">{count}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function RewardsList({ rewards }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Referral rewards</CardTitle>
        <CardDescription>
          Free Pro device-months you&apos;ve earned (capped at 3 devices for 3
          months).
        </CardDescription>
      </CardHeader>
      <CardContent>
        {rewards.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No rewards yet. Refer a friend to earn 1 device free for 1 month with
            full Pro features.
          </p>
        ) : (
          <ul className="space-y-3">
            {rewards.map((reward, idx) => {
              const granted = formatDate(reward.granted_at);
              const expires = formatDate(reward.expires_at);
              return (
                <li
                  key={`${reward.devices_granted}-${reward.months_granted}-${idx}`}
                  className="flex items-start gap-3 rounded-md border border-border bg-card p-4"
                >
                  <Gift size={24} className="mt-0.5 text-primary" />
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">
                      {reward.devices_granted}{" "}
                      {reward.devices_granted === 1 ? "device" : "devices"} free
                      for {reward.months_granted}{" "}
                      {reward.months_granted === 1 ? "month" : "months"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Full Pro features included.
                      {granted ? ` Granted ${granted}.` : ""}
                      {expires ? ` Expires ${expires}.` : ""}
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

export default function ReferralPage() {
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | succeeded | failed
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getReferralSummary();
        if (!cancelled) {
          setSummary(data);
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

  return (
    <section className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold text-primary">Refer &amp; earn</h1>
        <p className="text-sm text-muted-foreground">
          Invite friends and earn free Pro device-months when they join.
        </p>
      </header>

      {status === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : status === "failed" ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-destructive">
          {error || "Failed to load referrals"}
        </div>
      ) : (
        <>
          <ReferralCode code={summary.code} />
          <div className="grid gap-6 lg:grid-cols-2">
            <ReferralCount count={summary.count} />
            <RewardsList rewards={summary.rewards ?? []} />
          </div>
        </>
      )}
    </section>
  );
}
