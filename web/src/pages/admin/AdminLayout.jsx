import { NavLink, Outlet, Link } from "react-router-dom";
import { useState } from "react";
import {
  CaretDoubleLeft,
  CaretDoubleRight,
  Question,
  ArrowLeft,
  ShieldCheck,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import BrandMark from "@/components/BrandMark";
import CrashHelpDialog from "@/pages/admin/CrashHelpDialog";
import { ADMIN_NAV_GROUPS } from "@/lib/adminNav";

export default function AdminLayout() {
  const [helpOpen, setHelpOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="iotaps-admin-shell flex min-h-[calc(100vh-3.5rem)] flex-col lg:flex-row">
      <aside
        className={cn(
          "iotaps-admin-sidebar flex shrink-0 flex-col border-r border-border bg-card",
          collapsed ? "w-16" : "w-64"
        )}
      >
        <div className={cn("border-b border-border px-3 py-4", collapsed && "px-2")}>
          {!collapsed ? (
            <div className="flex items-center gap-2.5">
              <BrandMark size={28} className="rounded-sm" />
              <div>
                <p className="flex items-center gap-1.5 font-brand text-sm font-bold text-foreground">
                  <ShieldCheck size={16} weight="fill" className="text-primary" />
                  Platform admin
                </p>
                <p className="text-[10px] text-muted-foreground">Super-admin only</p>
              </div>
            </div>
          ) : (
            <ShieldCheck size={22} weight="fill" className="mx-auto text-primary" />
          )}
        </div>

        <div className="border-b border-border p-2">
          <Link
            to="/get-started"
            className={cn(
              "flex items-center gap-2 rounded-md px-2.5 py-2 text-xs font-semibold text-primary hover:bg-primary/10",
              collapsed && "justify-center px-2"
            )}
            title="Back to console"
          >
            <ArrowLeft size={16} />
            {!collapsed ? <span>Back to console</span> : null}
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto py-2" aria-label="Admin">
          {ADMIN_NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-3 px-2">
              {!collapsed ? (
                <p className="mb-1 px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </p>
              ) : (
                <div className="mx-auto mb-2 h-px w-8 bg-border" />
              )}
              <ul className="space-y-0.5">
                {group.items.map(({ to, end, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={end}
                      title={label}
                      className={({ isActive }) =>
                        cn(
                          "console-nav-item",
                          collapsed && "justify-center px-2",
                          isActive && "console-nav-item-active"
                        )
                      }
                    >
                      <Icon size={18} weight="duotone" />
                      {!collapsed ? <span className="truncate">{label}</span> : null}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className={cn(
            "console-nav-collapse flex w-full items-center gap-2 border-t border-border px-3 py-2.5 text-sidebar-muted hover:bg-muted/50",
            collapsed && "justify-center"
          )}
        >
          {collapsed ? <CaretDoubleRight size={16} /> : <CaretDoubleLeft size={16} />}
          {!collapsed ? <span>Collapse</span> : null}
        </button>
      </aside>

      <div className="iotaps-admin-main min-w-0 flex-1 overflow-auto">
        <div className="flex items-center justify-end gap-2 border-b border-border bg-muted/20 px-4 py-2 sm:px-6">
          <Button variant="outline" size="sm" onClick={() => setHelpOpen(true)}>
            <Question size={16} className="mr-1" />
            Server help
          </Button>
        </div>
        <div className="p-4 sm:p-6 lg:p-8">
          <Outlet />
        </div>
      </div>

      <CrashHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
