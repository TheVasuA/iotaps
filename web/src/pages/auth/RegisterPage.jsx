import { useState, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import ThemeModeToggle from "@/components/ThemeModeToggle";
import Logo from "@/components/Logo";
import { useAppDispatch } from "@/store/hooks";
import { setCredentials } from "@/store/authSlice";
import {
  register,
  login,
  loginWithGoogle,
  principalFromToken,
  extractApiError,
} from "@/lib/authApi";

export default function RegisterPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [referralCode, setReferralCode] = useState(params.get("ref") || "");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setSubmitting(true);
    try {
      await register({ email, password, referralCode });
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
      toast.success("Account created");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  const onGoogleCredential = useCallback(
    async (idToken) => {
      setSubmitting(true);
      try {
        const tokens = await loginWithGoogle({ idToken });
        const user = principalFromToken(tokens.access_token);
        if (user) {
          dispatch(
            setCredentials({
              user,
              accessToken: tokens.access_token,
              refreshToken: tokens.refresh_token,
            })
          );
          toast.success("Signed up with Google");
          navigate("/dashboard", { replace: true });
        }
      } catch (err) {
        toast.error(extractApiError(err).message);
      } finally {
        setSubmitting(false);
      }
    },
    [dispatch, navigate]
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-primary/5 p-10">
        <div>
          <Link to="/" className="flex items-center gap-2 text-2xl font-bold text-primary"><Logo size={28} />IoTAPS</Link>
          <p className="mt-1 text-xs text-muted-foreground">IoT Automation Platform Services</p>
        </div>
        <div className="space-y-4">
          <h2 className="text-3xl font-bold text-foreground leading-tight">
            Start managing your<br />IoT fleet today.
          </h2>
          <p className="text-muted-foreground max-w-md">
            Free to start. No credit card required. Provision devices, build dashboards, and automate — all in minutes.
          </p>
          <div className="flex gap-6 pt-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">Free</div>
              <div className="text-xs text-muted-foreground">5 Devices</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">Pro</div>
              <div className="text-xs text-muted-foreground">Unlimited</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-primary">24/7</div>
              <div className="text-xs text-muted-foreground">Support</div>
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} IoTAPS. All rights reserved.
        </p>
      </div>

      {/* Right panel — register form */}
      <div className="flex w-full flex-col lg:w-1/2 overflow-y-auto">
        {/* Top bar */}
        <div className="flex items-center justify-between px-6 py-3 shrink-0">
          <Link to="/" className="flex items-center gap-2 text-lg font-bold text-primary lg:hidden"><Logo size={20} />IoTAPS</Link>
          <div className="flex items-center gap-3">
            <ThemeModeToggle />
            <Link to="/login" className="text-sm font-medium text-muted-foreground hover:text-primary">
              Sign in
            </Link>
          </div>
        </div>

        {/* Form centered */}
        <div className="flex flex-1 items-center justify-center px-6 py-4">
          <div className="w-full max-w-sm space-y-4">
            <div>
              <h1 className="text-2xl font-bold">Create your account</h1>
              <p className="mt-1 text-sm text-muted-foreground">Get started with IoTAPS for free</p>
            </div>

            {/* Google sign-up */}
            <GoogleSignInButton
              onCredential={onGoogleCredential}
              disabled={submitting}
              label="Sign up with Google"
            />

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-background px-3 text-xs text-muted-foreground">or continue with email</span>
              </div>
            </div>

            {/* Email form */}
            <form className="space-y-3" onSubmit={onSubmit}>
              <div className="space-y-1">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-9"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Min. 8 characters"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-9"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="confirm">Confirm password</Label>
                <Input
                  id="confirm"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="h-9"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="referral">Referral code <span className="text-muted-foreground">(optional)</span></Label>
                <Input
                  id="referral"
                  placeholder="Enter code"
                  value={referralCode}
                  onChange={(e) => setReferralCode(e.target.value)}
                  className="h-9"
                />
              </div>
              <Button type="submit" className="w-full h-9" disabled={submitting}>
                {submitting ? "Creating account..." : "Create account"}
              </Button>
            </form>

            <p className="text-center text-xs text-muted-foreground">
              Already have an account?{" "}
              <Link to="/login" className="font-medium text-primary hover:underline">
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
