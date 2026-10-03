import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Key, LockKey } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import AuthShell from "@/components/AuthShell";
import { AuthField, authLinkClass } from "@/components/auth/AuthField";
import { confirmPasswordReset, extractApiError } from "@/lib/authApi";

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") || "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
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
      await confirmPasswordReset({ token, newPassword: password });
      toast.success("Password updated. Please sign in.");
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Enter the reset token from your email and choose a new password."
      footer={
        <Link to="/login" className={authLinkClass}>
          Back to log in
        </Link>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        <AuthField
          id="token"
          label="Reset token"
          icon={Key}
          required
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <AuthField
          id="password"
          label="New password"
          type="password"
          icon={LockKey}
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
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <Button type="submit" className="auth-submit-btn" disabled={submitting}>
          {submitting ? "Updating…" : "Update password"}
        </Button>
      </form>
    </AuthShell>
  );
}
