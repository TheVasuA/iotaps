import { NavLink, Outlet } from "react-router-dom";
import { useState } from "react";
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
  Lifebuoy,
  Terminal,
  Question,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import CrashHelpDialog from "@/pages/admin/CrashHelpDialog";

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
  { to: "/admin/recovery", label: "Disaster Recovery", icon: Lifebuoy },
  { to: "/admin/commands", label: "Command Reference", icon: Terminal },
];

export default function AdminLayout() {
  const [helpOpen, setHelpOpen] = useState(false);
  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-primary">Admin platform</h1>
          <p className="text-sm text-muted-foreground">
            Super_Admin control panel for companies, infrastructure, revenue, and
            platform operations.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => setHelpOpen(true)}
        >
          <Question size={16} className="mr-1" />
          Help: Server crashed?
        </Button>
      </header>
      <CrashHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
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
