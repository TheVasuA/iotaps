import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldCheck } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import AuthCard from "@/components/auth/AuthCard";
import { AuthField } from "@/components/auth/AuthField";
import { enable2fa, verify2fa, extractApiError } from "@/lib/authApi";

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
      navigate("/get-started");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-lg justify-center px-4 py-6">
      <AuthCard
        title="Two-factor authentication"
        subtitle="Add a second verification factor to protect your account."
      >
        <div className="mb-4 flex items-center justify-center gap-2 text-primary">
          <ShieldCheck size={28} weight="fill" aria-hidden />
        </div>
        {!secret ? (
          <Button onClick={onEnable} disabled={loading} className="auth-submit-btn">
            {loading ? "Generating…" : "Set up 2FA"}
          </Button>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="auth-label mb-2">1. Authenticator secret</p>
              <code className="block break-all rounded-none border border-zinc-200 bg-zinc-50 px-3 py-2.5 text-sm text-zinc-800">
                {secret}
              </code>
              {otpauthUri ? (
                <p className="mt-2 break-all text-xs text-zinc-500">otpauth URI: {otpauthUri}</p>
              ) : null}
            </div>
            <form className="space-y-4" onSubmit={onVerify}>
              <AuthField
                id="otp"
                label="2. Verification code"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                required
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
              />
              <Button type="submit" className="auth-submit-btn" disabled={verifying}>
                {verifying ? "Verifying…" : "Verify & enable"}
              </Button>
            </form>
          </div>
        )}
      </AuthCard>
    </div>
  );
}
