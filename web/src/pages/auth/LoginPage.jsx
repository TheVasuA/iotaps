import { useState, useCallback, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { EnvelopeSimple, LockKey, ArrowLeft, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import AuthShell from "@/components/AuthShell";
import { AuthField, AuthDivider, authLinkClass } from "@/components/auth/AuthField";
import { useAppDispatch } from "@/store/hooks";
import { setCredentials } from "@/store/authSlice";
import {
  login,
  loginWithGoogle,
  principalFromToken,
  extractApiError,
  decodeJwt,
} from "@/lib/authApi";
import { useGoogleRedirectCredential } from "@/lib/useGoogleRedirectCredential";

function emailFromIdToken(idToken) {
  const claims = decodeJwt(idToken);
  return claims?.email || "";
}

export default function LoginPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from || "/homepage";
  const reauthMessage = location.state?.message;

  useEffect(() => {
    if (reauthMessage) {
      toast.info(reauthMessage);
    }
  }, [reauthMessage]);

  const [step, setStep] = useState(1);
  const [authMethod, setAuthMethod] = useState("password");
  const [pendingGoogleToken, setPendingGoogleToken] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [useBackupCode, setUseBackupCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const finishLogin = useCallback(
    (tokens, knownEmail) => {
      const user = principalFromToken(tokens.access_token, knownEmail);
      if (!user) {
        toast.error("Received an invalid session token");
        return;
      }
      dispatch(
        setCredentials({
          user,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        })
      );
      navigate(redirectTo, { replace: true });
    },
    [dispatch, navigate, redirectTo]
  );

  const onGoogleCredential = useCallback(
    async (idToken) => {
      setSubmitting(true);
      try {
        const tokens = await loginWithGoogle({ idToken });
        finishLogin(tokens, emailFromIdToken(idToken));
      } catch (err) {
        const { code, message } = extractApiError(err);
        if (code === "twofa_required") {
          setPendingGoogleToken(idToken);
          setAuthMethod("google");
          setEmail(emailFromIdToken(idToken) || email);
          setStep(2);
          toast.info("Enter the code from your authenticator app");
        } else if (code === "authentication_error" || code === "oauth_not_configured") {
          toast.error(message || "Google sign-in was rejected.");
        } else {
          toast.error(message);
        }
      } finally {
        setSubmitting(false);
      }
    },
    [email]
  );

  useGoogleRedirectCredential(step === 1 ? onGoogleCredential : undefined);

  const onSubmitCredentials = async (e) => {
    e.preventDefault();
    setAuthMethod("password");
    setPendingGoogleToken(null);
    setSubmitting(true);
    try {
      const tokens = await login({ email, password });
      finishLogin(tokens, email);
    } catch (err) {
      const { code, message } = extractApiError(err);
      if (code === "twofa_required") {
        setStep(2);
        toast.info("Enter the code from your authenticator app");
      } else if (code === "password_reset_required") {
        toast.error("Password reset required.");
        navigate("/forgot-password", { state: { email } });
      } else {
        toast.error(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit2fa = async (e) => {
    e.preventDefault();
    if (!otp.trim()) {
      toast.error(useBackupCode ? "Enter your backup code" : "Enter your 6-digit code");
      return;
    }
    setSubmitting(true);
    try {
      let tokens;
      if (authMethod === "google" && pendingGoogleToken) {
        tokens = await loginWithGoogle({ idToken: pendingGoogleToken, otp: otp.trim() });
        finishLogin(tokens, emailFromIdToken(pendingGoogleToken) || email);
      } else {
        tokens = await login({ email, password, otp: otp.trim() });
        finishLogin(tokens, email);
      }
    } catch (err) {
      const { code, message } = extractApiError(err);
      if (code === "twofa_invalid") {
        toast.error("Invalid code — try again");
      } else {
        toast.error(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const is2faStep = step === 2;

  return (
    <AuthShell
      title={is2faStep ? "Two-factor authentication" : "Log In"}
      subtitle={
        is2faStep
          ? "Your account has 2FA enabled. Enter the code from your authenticator app."
          : undefined
      }
      footer={
        !is2faStep ? (
          <>
            Don&apos;t have an account yet?{" "}
            <Link to="/register" className={authLinkClass}>
              Sign Up
            </Link>
          </>
        ) : null
      }
    >
      <div className="space-y-6">
        {is2faStep ? (
          <>
            <button
              type="button"
              className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              onClick={() => {
                setStep(1);
                setOtp("");
                setUseBackupCode(false);
                setPendingGoogleToken(null);
                setAuthMethod("password");
              }}
            >
              <ArrowLeft size={16} />
              Back to sign in
            </button>

            <div className="flex flex-col items-center gap-2 py-2">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
                <ShieldCheck size={32} weight="duotone" />
              </span>
              <p className="text-center text-xs text-muted-foreground">
                {authMethod === "google" ? "Google sign-in" : "Signing in"} as{" "}
                <span className="font-medium text-foreground">{email || "your account"}</span>
              </p>
            </div>

            <form className="space-y-4" onSubmit={onSubmit2fa}>
              <AuthField
                id="otp"
                label={useBackupCode ? "Backup code" : "Authentication code"}
                inputMode={useBackupCode ? "text" : "numeric"}
                autoComplete="one-time-code"
                placeholder={useBackupCode ? "XXXX-XXXX" : "000000"}
                required
                maxLength={12}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\s/g, ""))}
                autoFocus
              />
              <button
                type="button"
                className="text-xs font-medium text-primary hover:underline"
                onClick={() => setUseBackupCode((b) => !b)}
              >
                {useBackupCode ? "Use authenticator app instead" : "Use a backup code instead"}
              </button>
              <Button type="submit" className="auth-submit-btn w-full" disabled={submitting}>
                {submitting ? "Verifying…" : "Verify & log in"}
              </Button>
            </form>
          </>
        ) : (
          <>
            <div className="auth-google-wrap">
              <GoogleSignInButton
                onCredential={onGoogleCredential}
                disabled={submitting}
                redirectReturnPath="/login"
              />
            </div>

            <AuthDivider label="or email" />

            <form className="space-y-4" onSubmit={onSubmitCredentials}>
              <AuthField
                id="email"
                label="Email"
                type="email"
                icon={EnvelopeSimple}
                placeholder="you@company.com"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <AuthField
                id="password"
                label="Password"
                type="password"
                icon={LockKey}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />

              <p className="text-center text-sm">
                <Link to="/forgot-password" className={authLinkClass}>
                  Forgot password?
                </Link>
              </p>

              <Button type="submit" className="auth-submit-btn w-full" disabled={submitting}>
                {submitting ? "Signing in…" : "Continue"}
              </Button>
            </form>
          </>
        )}
      </div>
    </AuthShell>
  );
}
