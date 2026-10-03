import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  User,
  ShieldCheck,
  Palette,
  Copy,
  Check,
  Key,
  Warning,
  GoogleLogo,
  LinkSimple,
  LinkBreak,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import OtpQrCode from "@/components/auth/OtpQrCode";
import { AuthField } from "@/components/auth/AuthField";
import GoogleSignInButton from "@/components/GoogleSignInButton";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectMode, setMode } from "@/store/authSlice";
import {
  changePassword,
  disable2fa,
  enable2fa,
  get2faStatus,
  getProfile,
  linkGoogleAccount,
  regenerateBackupCodes,
  setInitialPassword,
  unlinkGoogleAccount,
  updateProfile,
  verify2fa,
} from "@/lib/userAccountApi";
import { extractApiError } from "@/lib/authApi";
import { useGoogleRedirectCredential } from "@/lib/useGoogleRedirectCredential";
import { ACCOUNT_COMPANY } from "@/lib/accountTypes";

const TABS = [
  { id: "profile", label: "Profile", icon: User, desc: "Identity & workspace" },
  { id: "security", label: "Security", icon: ShieldCheck, desc: "Password, Google, 2FA" },
  { id: "preferences", label: "Preferences", icon: Palette, desc: "Theme & display" },
];

function accountTypeLabel(t) {
  if (t === ACCOUNT_COMPANY) return "Company";
  if (t === "student") return "Student";
  return "Individual";
}

function CopyButton({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setOk(true);
          setTimeout(() => setOk(false), 2000);
        } catch {
          toast.error("Copy failed");
        }
      }}
    >
      {ok ? <Check size={14} /> : <Copy size={14} />}
      {ok ? "Copied" : "Copy"}
    </button>
  );
}

export default function AccountSettingsPage() {
  const dispatch = useAppDispatch();
  const mode = useAppSelector(selectMode);
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "profile";

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [changingPw, setChangingPw] = useState(false);
  const [setPw, setSetPw] = useState("");
  const [setPwConfirm, setSetPwConfirm] = useState("");
  const [settingPw, setSettingPw] = useState(false);

  const [unlinkPw, setUnlinkPw] = useState("");
  const [linkingGoogle, setLinkingGoogle] = useState(false);
  const [unlinkingGoogle, setUnlinkingGoogle] = useState(false);

  const [twofaStatus, setTwofaStatus] = useState({ enabled: false, backup_codes_remaining: 0 });
  const [setupSecret, setSetupSecret] = useState(null);
  const [setupQr, setSetupQr] = useState(null);
  const [verifyOtp, setVerifyOtp] = useState("");
  const [newBackupCodes, setNewBackupCodes] = useState(null);
  const [disablePw, setDisablePw] = useState("");
  const [disableOtp, setDisableOtp] = useState("");
  const [regenPw, setRegenPw] = useState("");
  const [regenOtp, setRegenOtp] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, s] = await Promise.all([getProfile(), get2faStatus()]);
      setProfile(p);
      setDisplayName(p.display_name || "");
      setTwofaStatus(s);
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setTab = (id) => setParams({ tab: id });

  const saveProfile = async (e) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const updated = await updateProfile({ display_name: displayName.trim() || null });
      setProfile(updated);
      toast.success("Profile updated");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSavingProfile(false);
    }
  };

  const onSetPassword = async (e) => {
    e.preventDefault();
    if (setPw !== setPwConfirm) {
      toast.error("Passwords do not match");
      return;
    }
    setSettingPw(true);
    try {
      await setInitialPassword({ newPassword: setPw });
      toast.success("Password set — you can sign in with email");
      setSetPw("");
      setSetPwConfirm("");
      await load();
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSettingPw(false);
    }
  };

  const onChangePassword = async (e) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      toast.error("Passwords do not match");
      return;
    }
    setChangingPw(true);
    try {
      await changePassword({ currentPassword: currentPw, newPassword: newPw });
      toast.success("Password updated");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setChangingPw(false);
    }
  };

  const onLinkGoogle = async (idToken) => {
    setLinkingGoogle(true);
    try {
      const updated = await linkGoogleAccount({ idToken });
      setProfile(updated);
      toast.success("Google account linked");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setLinkingGoogle(false);
    }
  };

  const onUnlinkGoogle = async (e) => {
    e.preventDefault();
    setUnlinkingGoogle(true);
    try {
      const updated = await unlinkGoogleAccount({ password: unlinkPw });
      setProfile(updated);
      setUnlinkPw("");
      toast.success("Google sign-in unlinked");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setUnlinkingGoogle(false);
    }
  };

  const start2fa = async () => {
    try {
      const data = await enable2fa();
      setSetupSecret(data.secret);
      setSetupQr(data.qr);
      setNewBackupCodes(null);
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const confirm2fa = async (e) => {
    e.preventDefault();
    try {
      const data = await verify2fa({ otp: verifyOtp.trim() });
      setNewBackupCodes(data.backup_codes || []);
      setSetupSecret(null);
      setSetupQr(null);
      setVerifyOtp("");
      await load();
      toast.success("Two-factor authentication enabled");
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const onDisable2fa = async (e) => {
    e.preventDefault();
    try {
      await disable2fa({ password: disablePw, otp: disableOtp.trim() });
      toast.success("2FA disabled");
      setDisablePw("");
      setDisableOtp("");
      await load();
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const onRegenCodes = async (e) => {
    e.preventDefault();
    try {
      const data = await regenerateBackupCodes({ password: regenPw, otp: regenOtp.trim() });
      setNewBackupCodes(data.backup_codes || []);
      setRegenPw("");
      setRegenOtp("");
      await load();
      toast.success("New backup codes generated");
    } catch (err) {
      toast.error(extractApiError(err).message);
    }
  };

  const setTheme = (next) => {
    dispatch(setMode(next));
    updateProfile({ theme_mode: next }).catch(() => {
      toast.error("Could not save theme preference");
    });
  };

  const googleLinked = profile?.oauth_provider === "google";

  useGoogleRedirectCredential(
    !loading && !googleLinked
      ? (idToken) => {
          setParams({ tab: "security" });
          onLinkGoogle(idToken);
        }
      : undefined
  );

  if (loading && !profile) {
    return (
      <div className="settings-screen flex min-h-[calc(100dvh-3.75rem)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="settings-screen min-h-[calc(100dvh-3.75rem)] w-full">
      <div className="settings-screen-bg" aria-hidden />
      <div className="settings-layout">
        <aside className="settings-nav">
          <div className="settings-nav-head">
            <h1 className="font-brand text-xl font-bold">Account</h1>
            <p className="mt-1 text-xs text-muted-foreground">Manage your IoTAPS identity</p>
          </div>
          <nav className="settings-nav-list" aria-label="Settings sections">
            {TABS.map(({ id, label, icon: Icon, desc }) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={cn("settings-nav-item", tab === id && "settings-nav-item-active")}
              >
                <span className="settings-nav-icon">
                  <Icon size={20} weight={tab === id ? "duotone" : "regular"} />
                </span>
                <span className="min-w-0 text-left">
                  <span className="block text-sm font-semibold">{label}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{desc}</span>
                </span>
              </button>
            ))}
          </nav>
        </aside>

        <div className="settings-main">
          <header className="settings-profile-hero">
            <span className="settings-profile-avatar">
              {(displayName || profile?.email || "U").charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-bold">{displayName || profile?.email}</p>
              <p className="truncate text-sm text-muted-foreground">{profile?.email}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge variant="secondary">{accountTypeLabel(profile?.account_type)}</Badge>
                {googleLinked ? (
                  <Badge variant="outline" className="gap-1">
                    <GoogleLogo size={12} weight="bold" /> Google linked
                  </Badge>
                ) : (
                  <Badge variant="outline">Email sign-in</Badge>
                )}
                {twofaStatus.enabled ? (
                  <Badge variant="success">2FA on</Badge>
                ) : (
                  <Badge variant="muted">2FA off</Badge>
                )}
              </div>
            </div>
          </header>

          {tab === "profile" ? (
            <section className="settings-card">
              <h2 className="settings-card-title">Profile details</h2>
              <form onSubmit={saveProfile} className="mt-4 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="display-name">Display name</Label>
                    <Input
                      id="display-name"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="Your name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Email</Label>
                    <Input value={profile?.email || ""} disabled className="bg-muted/40" />
                  </div>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Organization</Label>
                    <p className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm font-medium">
                      {profile?.organization_name || "—"}
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>Role</Label>
                    <p className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-sm font-medium capitalize">
                      {profile?.role?.replace(/_/g, " ") || "—"}
                    </p>
                  </div>
                </div>
                <Button type="submit" disabled={savingProfile}>
                  {savingProfile ? "Saving…" : "Save profile"}
                </Button>
              </form>
              {profile?.account_type === ACCOUNT_COMPANY ? (
                <p className="mt-4 text-sm text-muted-foreground">
                  Team members:{" "}
                  <Link to="/org/users" className="font-semibold text-primary hover:underline">
                    Organization users
                  </Link>
                </p>
              ) : null}
            </section>
          ) : null}

          {tab === "security" ? (
            <div className="space-y-6">
              <section className="settings-card">
                <h2 className="settings-card-title flex items-center gap-2">
                  <GoogleLogo size={22} weight="duotone" className="text-primary" />
                  Google sign-in
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Link the Google account that matches your IoTAPS email for one-click sign-in.
                </p>
                {googleLinked ? (
                  <div className="mt-4 space-y-4">
                    <div className="flex items-center gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm">
                      <LinkSimple size={18} className="text-primary" />
                      <span>
                        Connected as <strong>{profile?.email}</strong>
                      </span>
                    </div>
                    <form onSubmit={onUnlinkGoogle} className="max-w-md space-y-3">
                      <p className="text-xs text-muted-foreground">
                        Unlinking requires your account password so you can still sign in with email.
                      </p>
                      <AuthField
                        id="unlink-pw"
                        label="Password"
                        type="password"
                        value={unlinkPw}
                        onChange={(e) => setUnlinkPw(e.target.value)}
                        required
                      />
                      <Button type="submit" variant="outline" disabled={unlinkingGoogle}>
                        <LinkBreak size={16} className="mr-2" />
                        {unlinkingGoogle ? "Unlinking…" : "Unlink Google"}
                      </Button>
                    </form>
                  </div>
                ) : (
                  <div className="mt-4 max-w-sm">
                    <GoogleSignInButton
                      label="Link Google account"
                      onCredential={onLinkGoogle}
                      disabled={linkingGoogle}
                      redirectReturnPath="/settings?tab=security"
                    />
                  </div>
                )}
              </section>

              <section className="settings-card">
                <h2 className="settings-card-title flex items-center gap-2">
                  <Key size={20} className="text-primary" />
                  Password
                </h2>
                {!profile?.has_password ? (
                  <form onSubmit={onSetPassword} className="mt-4 grid max-w-md gap-3">
                    <p className="text-sm text-muted-foreground">
                      Set a password to sign in with email or unlink Google later.
                    </p>
                    <AuthField
                      id="set-pw"
                      label="New password"
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      value={setPw}
                      onChange={(e) => setSetPw(e.target.value)}
                      required
                    />
                    <AuthField
                      id="set-pw2"
                      label="Confirm password"
                      type="password"
                      value={setPwConfirm}
                      onChange={(e) => setSetPwConfirm(e.target.value)}
                      required
                    />
                    <Button type="submit" disabled={settingPw}>
                      {settingPw ? "Saving…" : "Set password"}
                    </Button>
                  </form>
                ) : (
                  <form onSubmit={onChangePassword} className="mt-4 grid max-w-md gap-3">
                    <AuthField
                      id="cur-pw"
                      label="Current password"
                      type="password"
                      autoComplete="current-password"
                      value={currentPw}
                      onChange={(e) => setCurrentPw(e.target.value)}
                      required
                    />
                    <AuthField
                      id="new-pw"
                      label="New password"
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      value={newPw}
                      onChange={(e) => setNewPw(e.target.value)}
                      required
                    />
                    <AuthField
                      id="conf-pw"
                      label="Confirm new password"
                      type="password"
                      value={confirmPw}
                      onChange={(e) => setConfirmPw(e.target.value)}
                      required
                    />
                    <Button type="submit" disabled={changingPw}>
                      {changingPw ? "Updating…" : "Update password"}
                    </Button>
                  </form>
                )}
              </section>

              <section className="settings-card">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="settings-card-title flex items-center gap-2">
                    <ShieldCheck size={20} className="text-primary" />
                    Two-factor authentication
                  </h2>
                  {twofaStatus.enabled ? (
                    <Badge variant="success">Enabled</Badge>
                  ) : (
                    <Badge variant="muted">Off</Badge>
                  )}
                </div>

                {newBackupCodes?.length ? (
                  <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
                    <p className="flex items-center gap-2 text-sm font-bold text-amber-800 dark:text-amber-200">
                      <Warning size={18} />
                      Save these backup codes now
                    </p>
                    <ul className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm sm:grid-cols-3">
                      {newBackupCodes.map((c) => (
                        <li
                          key={c}
                          className="rounded-md border border-border bg-background px-2 py-1 text-center"
                        >
                          {c}
                        </li>
                      ))}
                    </ul>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => {
                        navigator.clipboard.writeText(newBackupCodes.join("\n"));
                        toast.success("Codes copied");
                      }}
                    >
                      Copy all codes
                    </Button>
                  </div>
                ) : null}

                {!twofaStatus.enabled ? (
                  !setupSecret ? (
                    <Button type="button" className="mt-4" onClick={start2fa}>
                      Set up authenticator app
                    </Button>
                  ) : (
                    <div className="mt-4 grid gap-6 md:grid-cols-2">
                      <div className="flex flex-col items-center gap-3">
                        <OtpQrCode uri={setupQr} />
                        <p className="text-center text-xs text-muted-foreground">
                          Scan with Google Authenticator, Authy, or 1Password
                        </p>
                      </div>
                      <div className="space-y-3">
                        <div>
                          <p className="text-xs font-bold uppercase text-muted-foreground">Manual key</p>
                          <code className="mt-1 block break-all rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs">
                            {setupSecret}
                          </code>
                          <CopyButton text={setupSecret} />
                        </div>
                        <form onSubmit={confirm2fa} className="space-y-3">
                          <AuthField
                            id="verify-otp"
                            label="Verification code"
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            placeholder="000000"
                            value={verifyOtp}
                            onChange={(e) => setVerifyOtp(e.target.value)}
                            required
                          />
                          <Button type="submit" className="w-full">
                            Verify & enable 2FA
                          </Button>
                        </form>
                      </div>
                    </div>
                  )
                ) : (
                  <div className="mt-4 space-y-6">
                    <p className="text-sm text-muted-foreground">
                      Backup codes remaining: <strong>{twofaStatus.backup_codes_remaining}</strong>
                    </p>
                    <form
                      onSubmit={onRegenCodes}
                      className="max-w-md space-y-3 rounded-lg border border-border p-4"
                    >
                      <p className="text-sm font-semibold">Regenerate backup codes</p>
                      {profile?.has_password ? (
                        <AuthField
                          id="regen-pw"
                          label="Password"
                          type="password"
                          value={regenPw}
                          onChange={(e) => setRegenPw(e.target.value)}
                          required
                        />
                      ) : null}
                      <AuthField
                        id="regen-otp"
                        label="Authenticator code"
                        inputMode="numeric"
                        value={regenOtp}
                        onChange={(e) => setRegenOtp(e.target.value)}
                        required
                      />
                      <Button type="submit" variant="outline" size="sm">
                        Generate new codes
                      </Button>
                    </form>
                    <form
                      onSubmit={onDisable2fa}
                      className="max-w-md space-y-3 rounded-lg border border-destructive/30 p-4"
                    >
                      <p className="text-sm font-semibold text-destructive">Disable 2FA</p>
                      {profile?.has_password ? (
                        <AuthField
                          id="dis-pw"
                          label="Password"
                          type="password"
                          value={disablePw}
                          onChange={(e) => setDisablePw(e.target.value)}
                          required
                        />
                      ) : null}
                      <AuthField
                        id="dis-otp"
                        label="Authenticator or backup code"
                        value={disableOtp}
                        onChange={(e) => setDisableOtp(e.target.value)}
                        required
                      />
                      <Button type="submit" variant="destructive" size="sm">
                        Disable two-factor
                      </Button>
                    </form>
                  </div>
                )}
              </section>
            </div>
          ) : null}

          {tab === "preferences" ? (
            <section className="settings-card">
              <h2 className="settings-card-title">Appearance</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Console theme — saved to your account.
              </p>
              <div className="mt-4 flex gap-2">
                <Button
                  type="button"
                  variant={mode === "light" ? "default" : "outline"}
                  onClick={() => setTheme("light")}
                >
                  Light
                </Button>
                <Button
                  type="button"
                  variant={mode === "dark" ? "default" : "outline"}
                  onClick={() => setTheme("dark")}
                >
                  Dark
                </Button>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
