import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { SignOut, ShieldCheck } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import Logo from "./Logo";
import ThemeModeToggle from "./ThemeModeToggle";
import NotificationCenter from "./notifications/NotificationCenter";
import WhatsNewPopup from "./changelog/WhatsNewPopup";
import useNotifications from "@/lib/useNotifications";
import { Button } from "@/components/ui/button";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { logoutAndRevoke, selectUser, selectRole } from "@/store/authSlice";

// Authenticated shell layout. Real per-role navigation is built in the
// dashboard/admin tasks (8.x, 20.x). This frames routed content and exposes the
// theme toggle, 2FA setup link, and sign-out (Req 1.6).
const navItems = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/devices", label: "Devices" },
  { to: "/explorer", label: "IoT Explorer" },
  { to: "/flasher", label: "Flasher" },
  { to: "/rules", label: "Rules" },
  { to: "/billing", label: "Billing" },
  { to: "/referrals", label: "Referrals" },
  { to: "/wallet", label: "Wallet" },
  { to: "/support", label: "Support" },
];

export default function AppLayout() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const user = useAppSelector(selectUser);
  const role = useAppSelector(selectRole);

  // Bridge in-app notifications from the WebSocket into the store (Req 20.2).
  useNotifications();

  // Super_Admin gets an extra "Admin" entry into the platform control panel
  // (Req 23-29). Built in task 20.7.
  const items =
    role === "super_admin"
      ? [...navItems, { to: "/admin", label: "Admin" }]
      : navItems;

  const onLogout = async () => {
    await dispatch(logoutAndRevoke());
    navigate("/", { replace: true });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2 text-lg font-semibold text-primary" title="IoT Automation Platform Services">
            <Logo size={22} />
            IoTAPS
          </span>
          <nav className="flex gap-1">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-accent",
                    isActive && "bg-accent text-accent-foreground"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <NavLink
            to="/security/2fa"
            className={({ isActive }) =>
              cn(
                "inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-foreground transition-colors hover:bg-accent",
                isActive && "bg-accent text-accent-foreground"
              )
            }
            aria-label="Two-factor authentication"
            title="Two-factor authentication"
          >
            <ShieldCheck size={18} />
          </NavLink>
          <NotificationCenter />
          <ThemeModeToggle />
          <div className="hidden sm:flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold uppercase">
              {user?.email ? user.email.charAt(0) : "U"}
            </div>
            <span className="text-sm text-foreground truncate max-w-[140px]" title={user?.email}>
              {user?.email ? user.email.split("@")[0] : "User"}
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={onLogout} className="text-muted-foreground hover:text-destructive">
            <SignOut size={16} />
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </header>
      <main className="p-6">
        <Outlet />
      </main>
      {/* "What's new" popup on sign-in when unseen changelog entries exist (Req 22.2). */}
      <WhatsNewPopup />
    </div>
  );
}
