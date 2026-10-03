import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { EnvelopeSimple } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import AuthShell from "@/components/AuthShell";
import { AuthField, authLinkClass } from "@/components/auth/AuthField";
import { requestPasswordReset, extractApiError } from "@/lib/authApi";

export default function ForgotPasswordPage() {
  const location = useLocation();
  const [email, setEmail] = useState(location.state?.email || "");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await requestPasswordReset({ email });
      setSent(true);
      toast.success("If that account exists, a reset link has been sent");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Reset password"
      subtitle="We'll email you a link to reset your password."
      footer={
        <Link to="/login" className={authLinkClass}>
          Back to log in
        </Link>
      }
    >
      {sent ? (
        <p className="text-center text-sm leading-relaxed text-zinc-600">
          If an account exists for <span className="font-semibold text-zinc-900">{email}</span>,
          you&apos;ll receive an email with a reset link shortly. Already have a token?{" "}
          <Link to="/reset-password" className={authLinkClass}>
            Enter it here
          </Link>
          .
        </p>
      ) : (
        <form className="space-y-4" onSubmit={onSubmit}>
          <AuthField
            id="email"
            label="Email"
            type="email"
            icon={EnvelopeSimple}
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" className="auth-submit-btn" disabled={submitting}>
            {submitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
