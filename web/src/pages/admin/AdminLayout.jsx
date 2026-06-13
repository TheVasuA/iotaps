import { NavLink, Outlet } from "react-router-dom";
import {
  ChartPie,
  Buildings,
  HardDrives,
  CurrencyInr,
  Tag,
  FileText,
  Heartbeat,
  ShieldCheck,
  Gauge,
  Users,
  DeviceMobile,
  Timer,
  Wrench,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

// Super_Admin admin platform shell (Task 20.7, Req 23-29). Renders the purple
// Super_Admin theme (data-theme="admin" is applied at login via the auth slice,
// Req 4.1) and a side navigation across the admin panels. The routed panel
// content renders in the <Outlet />.
const panels = [
  { to: "/admin", end: true, label: "Overview", icon: ChartPie },
  { to: "/admin/system", label: "System Stats", icon: Gauge },
  { to: "/admin/companies", label: "Companies & Users", icon: Buildings },
  { to: "/admin/mqtt-nodes", label: "MQTT Nodes", icon: HardDrives },
  { to: "/admin/revenue", label: "Revenue", icon: CurrencyInr },
  { to: "/admin/coupons", label: "Coupons & Referrals", icon: Tag },
  { to: "/admin/content", label: "Content", icon: FileText },
  { to: "/admin/health", label: "Health & Errors", icon: Heartbeat },
  { to: "/admin/security", label: "Security & Settings", icon: ShieldCheck },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/devices-overview", label: "All Devices", icon: DeviceMobile },
  { to: "/admin/expiring", label: "Expiring", icon: Timer },
  { to: "/admin/controls", label: "Controls", icon: Wrench },
];

export default function AdminLayout() {
  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-primary">Admin platform</h1>
        <p className="text-sm text-muted-foreground">
          Super_Admin control panel for companies, infrastructure, revenue, and
          platform operations.
        </p>
      </header>
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="flex flex-row flex-wrap gap-1 lg:flex-col">
          {panels.map(({ to, end, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive
                    ? "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground"
                    : "text-foreground"
                )
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
