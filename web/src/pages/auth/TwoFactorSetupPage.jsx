import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { enable2fa, verify2fa, extractApiError } from "@/lib/authApi";

// Two-factor setup (Req 1.8). Authenticated users provision a TOTP secret via
// /auth/2fa/enable (returns secret + otpauth URI), scan it into an authenticator
// app, then confirm a code via /auth/2fa/verify to enable 2FA on the account.
export default function TwoFactorSetupPage() {
  const navigate = useNavigate();
  const [secret, setSecret] = useState(null);
  const [otpauthUri, setOtpauthUri] = useState(null);
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const onEnable = useCallback(async () => {
    setLoading(true);
    try {
      const data = await enable2fa();
      setSecret(data.secret);
      setOtpauthUri(data.qr);
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const onVerify = async (e) => {
    e.preventDefault();
    setVerifying(true);
    try {
      await verify2fa({ otp });
      toast.success("Two-factor authentication enabled");
      navigate("/dashboard");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-primary">
            <ShieldCheck size={24} weight="fill" />
            <CardTitle className="text-xl">Two-factor authentication</CardTitle>
          </div>
          <CardDescription>
            Add a second verification factor to protect your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!secret ? (
            <Button onClick={onEnable} disabled={loading} className="w-full">
              {loading ? "Generating..." : "Set up 2FA"}
            </Button>
          ) : (
            <>
              <div className="space-y-2">
                <Label>1. Add this secret to your authenticator app</Label>
                <code className="block break-all rounded-md border border-border bg-muted px-3 py-2 text-sm">
                  {secret}
                </code>
                {otpauthUri ? (
                  <p className="text-xs text-muted-foreground break-all">
                    otpauth URI: {otpauthUri}
                  </p>
                ) : null}
              </div>
              <form className="space-y-3" onSubmit={onVerify}>
                <div className="space-y-2">
                  <Label htmlFor="otp">2. Enter the 6-digit code</Label>
                  <Input
                    id="otp"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="123456"
                    required
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={verifying}>
                  {verifying ? "Verifying..." : "Verify & enable"}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
