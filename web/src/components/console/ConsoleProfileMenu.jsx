import { useEffect, useRef, useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Gear,
  SignOut,
  Sun,
  Moon,
  CaretDown,
  CreditCard,
  Headset,
  User,
  Code,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { logoutAndRevoke, selectUser, selectMode, setMode } from "@/store/authSlice";
import { ACCOUNT_COMPANY } from "@/lib/accountTypes";

const DEV_MODE_KEY = "iotaps.console.devMode";

function displayNameFromEmail(email) {
  if (!email) return "User";
  const local = email.split("@")[0];
  return local.charAt(0).toUpperCase() + local.slice(1);
}

function planLabel(user) {
  return user?.plan === "pro" ? "Pro" : "Free";
}

export default function ConsoleProfileMenu() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const user = useAppSelector(selectUser);
  const mode = useAppSelector(selectMode);
  const [open, setOpen] = useState(false);
  const [devMode, setDevMode] = useState(() => {
    try {
      return localStorage.getItem(DEV_MODE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const rootRef = useRef(null);

  const name = useMemo(() => displayNameFromEmail(user?.email), [user?.email]);
  const initial = (name.charAt(0) || "U").toUpperCase();
  const email = user?.email || "—";

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const onLogout = async () => {
    setOpen(false);
    await dispatch(logoutAndRevoke());
    navigate("/", { replace: true });
  };

  const toggleDevMode = () => {
    const next = !devMode;
    setDevMode(next);
    try {
      localStorage.setItem(DEV_MODE_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  const setTheme = (next) => {
    dispatch(setMode(next));
    const applied = document.documentElement.classList.contains("dark");
    if ((next === "dark") !== applied) {
      toast.error("Could not switch theme mode");
    }
  };

  const quickLinks = [
    { to: "/settings", label: "Account", icon: User, desc: "Profile & security" },
    { to: "/billing", label: "Billing", icon: CreditCard, desc: "Plan & usage" },
    { to: "/support", label: "Support", icon: Headset, desc: "Help & chat" },
  ];

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className={cn("console-profile-trigger", open && "console-profile-trigger-open")}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="console-profile-avatar">{initial}</span>
        <span className="console-profile-trigger-meta hidden lg:flex">
          <span className="truncate font-semibold leading-tight text-foreground">{name}</span>
          <span className="truncate text-[11px] leading-tight text-muted-foreground">{email}</span>
        </span>
        <span className="console-profile-chevron hidden lg:inline-flex">
          <CaretDown size={12} weight="bold" />
        </span>
      </button>

      {open ? (
        <div className="console-profile-menu" role="menu">
          <div className="console-profile-menu-hero">
            <div className="console-profile-menu-hero-grid" aria-hidden />
            <div className="relative flex items-start gap-3">
              <span className="console-profile-avatar console-profile-avatar-lg">{initial}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-base font-bold text-foreground">{name}</p>
                <p className="truncate text-xs text-muted-foreground">{email}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="console-profile-chip">{planLabel(user)} plan</span>
                  {user?.account_type === ACCOUNT_COMPANY && user?.organization_name ? (
                    <span className="console-profile-chip console-profile-chip-muted">
                      {user.organization_name}
                    </span>
                  ) : null}
                </div>
              </div>
              <Link
                to="/settings"
                className="console-bar-icon-btn h-9 w-9 shrink-0"
                aria-label="Account settings"
                onClick={() => setOpen(false)}
              >
                <Gear size={18} weight="duotone" />
              </Link>
            </div>
          </div>

          <div className="console-profile-menu-body">
            <p className="console-profile-section-label">Shortcuts</p>
            <ul className="console-profile-link-grid">
              {quickLinks.map(({ to, label, icon: Icon, desc }) => (
                <li key={to}>
                  <Link
                    to={to}
                    className="console-profile-link-card"
                    onClick={() => setOpen(false)}
                  >
                    <span className="console-profile-link-icon">
                      <Icon size={20} weight="duotone" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-foreground">{label}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">{desc}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>

            <p className="console-profile-section-label mt-4">Preferences</p>
            <div className="console-profile-pref-row">
              <span className="text-sm font-medium text-foreground">Appearance</span>
              <div className="console-theme-switch" role="group" aria-label="Theme">
                <button
                  type="button"
                  className={cn(mode === "light" && "is-active")}
                  aria-label="Light mode"
                  onClick={() => setTheme("light")}
                >
                  <Sun size={16} weight={mode === "light" ? "fill" : "regular"} />
                </button>
                <button
                  type="button"
                  className={cn(mode === "dark" && "is-active")}
                  aria-label="Dark mode"
                  onClick={() => setTheme("dark")}
                >
                  <Moon size={16} weight={mode === "dark" ? "fill" : "regular"} />
                </button>
              </div>
            </div>
            <div className="console-profile-pref-row">
              <div className="flex items-center gap-2 text-sm">
                <Code size={16} className="text-muted-foreground" />
                <span className="font-medium">Developer mode</span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={devMode}
                className={cn("console-switch", devMode && "console-switch-on")}
                onClick={toggleDevMode}
              >
                <span className="console-switch-knob" />
              </button>
            </div>
            <div className="console-profile-pref-row border-0 pb-0">
              <span className="text-sm text-muted-foreground">Locale</span>
              <span className="text-sm font-medium text-foreground">English</span>
            </div>
          </div>

          <button type="button" className="console-profile-logout" onClick={onLogout}>
            <SignOut size={18} weight="bold" />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
