import { useState, useCallback } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import ThemeModeToggle from "@/components/ThemeModeToggle";
import { useAppDispatch } from "@/store/hooks";
import { setCredentials } from "@/store/authSlice";
import {
  login,
  loginWithGoogle,
  principalFromToken,
  extractApiError,
} from "@/lib/authApi";

export default function LoginPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needsOtp, setNeedsOtp] = useState(false);
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

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const tokens = await login({ email, password, otp: needsOtp ? otp : undefined });
      finishLogin(tokens, email);
    } catch (err) {
      const { code, message } = extractApiError(err);
      if (code === "twofa_required") {
        setNeedsOtp(true);
        toast.info("Enter your two-factor authentication code");
      } else if (code === "twofa_invalid") {
        toast.error("Invalid authentication code");
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

  const onGoogleCredential = useCallback(
    async (idToken) => {
      setSubmitting(true);
      try {
        const tokens = await loginWithGoogle({ idToken });
        finishLogin(tokens);
      } catch (err) {
        toast.error(extractApiError(err).message);
      } finally {
        setSubmitting(false);
      }
    },
    [finishLogin]
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-primary/5 p-10">
        <div>
          <Link to="/" className="text-2xl font-bold text-primary">IoTAPS</Link>
          <p className="mt-1 text-xs text-muted-foreground">IoT Automation Platform Services</p>
        </div>
        <div className="space-y-4">
          <h2 className="text-3xl font-bold text-foreground leading-tight">
            Monitor. Automate.<br />Control your fleet.
          </h2>
          <p className="text-muted-foreground max-w-md">
            Real-time dashboards, visual rule engine, OTA updates, and billing — all from one platform built for scale.
          </p>
          <div className="flex gap-6 pt-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">10M+</div>
              <div className="text-xs text-muted-foreground">Devices</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">99.9%</div>
              <div className="text-xs text-muted-foreground">Uptime</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">79ms</div>
              <div className="text-xs text-muted-foreground">Latency</div>
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} IoTAPS. All rights reserved.
        </p>
      </div>

      {/* Right panel — login form */}
      <div className="flex w-full flex-col lg:w-1/2">
        {/* Top bar */}
        <div className="flex items-center justify-between px-6 py-3 shrink-0">
          <Link to="/" className="text-lg font-bold text-primary lg:hidden">IoTAPS</Link>
          <div className="flex items-center gap-3">
            <ThemeModeToggle />
            <Link to="/register" className="text-sm font-medium text-muted-foreground hover:text-primary">
              Create account
            </Link>
          </div>
        </div>

        {/* Form centered */}
        <div className="flex flex-1 items-center justify-center px-6 py-4">
          <div className="w-full max-w-sm space-y-5">
            <div>
              <h1 className="text-2xl font-bold">Welcome back</h1>
              <p className="mt-1 text-sm text-muted-foreground">Sign in to your account</p>
            </div>

            {/* Google sign-in — prominent, separate from form */}
            <GoogleSignInButton onCredential={onGoogleCredential} disabled={submitting} />

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-background px-3 text-xs text-muted-foreground">or continue with email</span>
              </div>
            </div>

            {/* Email/password form */}
            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={needsOtp}
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password">Password</Label>
                  <Link
                    to="/forgot-password"
                    className="text-xs text-primary hover:underline"
                  >
                    Forgot?
                  </Link>
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={needsOtp}
                />
              </div>

              {needsOtp && (
                <div className="space-y-1.5">
                  <Label htmlFor="otp">2FA Code</Label>
                  <Input
                    id="otp"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="123456"
                    required
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    autoFocus
                  />
                </div>
              )}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? "Signing in..." : needsOtp ? "Verify & sign in" : "Sign in"}
              </Button>
            </form>

            <p className="text-center text-xs text-muted-foreground">
              Don&apos;t have an account?{" "}
              <Link to="/register" className="font-medium text-primary hover:underline">
                Sign up free
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
