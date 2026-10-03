import { useState, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EnvelopeSimple, LockKey, ArrowLeft, User, GraduationCap, Buildings } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import AuthShell from "@/components/AuthShell";
import { AuthField, AuthDivider, authLinkClass } from "@/components/auth/AuthField";
import { useAppDispatch } from "@/store/hooks";
import { setCredentials } from "@/store/authSlice";
import {
  register,
  login,
  loginWithGoogle,
  principalFromToken,
  extractApiError,
} from "@/lib/authApi";
import { useGoogleRedirectCredential } from "@/lib/useGoogleRedirectCredential";
import {
  ACCOUNT_COMPANY,
  ACCOUNT_INDIVIDUAL,
  SIGNUP_ACCOUNT_OPTIONS,
} from "@/lib/accountTypes";
import { cn } from "@/lib/utils";

const TYPE_ICONS = {
  individual: User,
  student: GraduationCap,
  company: Buildings,
};

export default function RegisterPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [step, setStep] = useState(1);
  const [signupMethod, setSignupMethod] = useState(null); // 'email' | 'google'
  const [pendingGoogleToken, setPendingGoogleToken] = useState(null);

  const [accountType, setAccountType] = useState(ACCOUNT_INDIVIDUAL);
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [referralCode, setReferralCode] = useState(params.get("ref") || "");
  const [submitting, setSubmitting] = useState(false);

  const goStep2Email = (e) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setSignupMethod("email");
    setPendingGoogleToken(null);
    setStep(2);
  };

  const onGoogleCredentialStep1 = useCallback((idToken) => {
    setSignupMethod("google");
    setPendingGoogleToken(idToken);
    setStep(2);
  }, []);

  useGoogleRedirectCredential(step === 1 ? onGoogleCredentialStep1 : undefined);

  const finishSignup = async () => {
    if (accountType === ACCOUNT_COMPANY && !organizationName.trim()) {
      toast.error("Enter your organization name");
      return;
    }
    setSubmitting(true);
    try {
      if (signupMethod === "google" && pendingGoogleToken) {
        const tokens = await loginWithGoogle({
          idToken: pendingGoogleToken,
          accountType,
          organizationName:
            accountType === ACCOUNT_COMPANY ? organizationName.trim() : undefined,
        });
        const user = principalFromToken(tokens.access_token);
        if (!user) {
          toast.error("Sign up failed");
          return;
        }
        dispatch(
          setCredentials({
            user,
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
          })
        );
        toast.success("Welcome to IoTAPS");
        navigate("/get-started", { replace: true });
        return;
      }

      await register({
        email,
        password,
        referralCode,
        accountType,
        organizationName: accountType === ACCOUNT_COMPANY ? organizationName.trim() : undefined,
      });
      const tokens = await login({ email, password });
      const user = principalFromToken(tokens.access_token, email);
      if (!user) {
        toast.success("Account created. Please sign in.");
        navigate("/login");
        return;
      }
      dispatch(
        setCredentials({
          user,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
        })
      );
      toast.success("Welcome to IoTAPS");
      navigate("/get-started", { replace: true });
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  const stepTitle = step === 1 ? "Create your account" : "Choose account type";
  const stepSubtitle =
    step === 1
      ? "Sign up with Google or email — you’ll pick Individual, Student, or Company next."
      : signupMethod === "google"
        ? "How will you use IoTAPS?"
        : "How will you use IoTAPS?";

  return (
    <AuthShell
      title={stepTitle}
      subtitle={stepSubtitle}
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className={authLinkClass}>
            Log In
          </Link>
        </>
      }
    >
      <div className="space-y-6">
        {step === 1 ? (
          <>
            <div className="auth-google-wrap">
              <GoogleSignInButton
                onCredential={onGoogleCredentialStep1}
                disabled={submitting}
                label="Continue with Google"
              />
            </div>

            <AuthDivider label="or email" />

            <form className="space-y-4" onSubmit={goStep2Email}>
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
                placeholder="Min. 8 characters"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <AuthField
                id="confirm"
                label="Confirm password"
                type="password"
                icon={LockKey}
                placeholder="••••••••"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              <AuthField
                id="referral"
                label="Referral code (optional)"
                placeholder="Enter code"
                value={referralCode}
                onChange={(e) => setReferralCode(e.target.value)}
              />
              <Button type="submit" className="auth-submit-btn w-full">
                Continue
              </Button>
            </form>
          </>
        ) : (
          <>
            <button
              type="button"
              className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              onClick={() => {
                setStep(1);
                if (signupMethod === "google") {
                  setPendingGoogleToken(null);
                  setSignupMethod(null);
                }
              }}
            >
              <ArrowLeft size={16} />
              Back
            </button>

            {signupMethod === "google" ? (
              <p className="rounded-lg bg-muted/50 px-3 py-2 text-center text-xs text-muted-foreground">
                Google account linked — select your workspace type to finish.
              </p>
            ) : null}

            <div className="auth-type-list space-y-2">
              {SIGNUP_ACCOUNT_OPTIONS.map((opt) => {
                const Icon = TYPE_ICONS[opt.id] || User;
                const selected = accountType === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setAccountType(opt.id)}
                    className={cn(
                      "auth-type-option flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition",
                      selected
                        ? "border-primary bg-primary/10 ring-1 ring-primary/25"
                        : "border-border bg-card hover:border-primary/35"
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                        selected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                      )}
                    >
                      <Icon size={22} weight={selected ? "fill" : "duotone"} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-bold text-foreground">{opt.title}</span>
                      <span className="block text-xs text-muted-foreground">{opt.subtitle}</span>
                    </span>
                    <span
                      className={cn(
                        "h-4 w-4 shrink-0 rounded-full border-2",
                        selected ? "border-primary bg-primary" : "border-muted-foreground/40"
                      )}
                      aria-hidden
                    />
                  </button>
                );
              })}
            </div>

            {accountType === ACCOUNT_COMPANY ? (
              <AuthField
                id="org-name"
                label="Organization name"
                placeholder="Your company or team name"
                required
                value={organizationName}
                onChange={(e) => setOrganizationName(e.target.value)}
              />
            ) : null}

            <Button
              type="button"
              className="auth-submit-btn w-full"
              disabled={submitting}
              onClick={finishSignup}
            >
              {submitting ? "Creating account…" : "Create account"}
            </Button>
          </>
        )}
      </div>
    </AuthShell>
  );
}
