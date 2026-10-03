import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { CaretDoubleLeft, CaretDoubleRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import BrandMark from "@/components/BrandMark";
import { cn } from "@/lib/utils";
import { getConsoleNavGroups } from "@/lib/consoleNav";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { fetchDashboards, selectDashboardsStatus, selectHomepageId } from "@/store/dashboardsSlice";

function navItemKey(item) {
  if (item.to) return `${item.label}:${item.to}`;
  return item.label;
}

export default function ConsoleSidebar({ user, role, collapsed, onToggleCollapsed, className }) {
  const dispatch = useAppDispatch();
  const status = useAppSelector(selectDashboardsStatus);
  const homepageId = useAppSelector(selectHomepageId);

  useEffect(() => {
    if (status === "idle") dispatch(fetchDashboards());
  }, [dispatch, status]);

  const groups = getConsoleNavGroups(user, role, { hasHomepage: Boolean(homepageId) });

  const onNavSoon = (label) => {
    toast.info(`${label} — coming soon`);
  };

  return (
    <aside className={cn("console-sidebar", className)}>
      <div className="console-sidebar-accent" aria-hidden />
      <div className="console-sidebar-inner">
        <header className={cn("console-sidebar-header", collapsed && "console-sidebar-header-collapsed")}>
          <NavLink
            to="/get-started"
            className="console-sidebar-brand"
            title="IoTAPS Console home"
          >
            <BrandMark size={collapsed ? 32 : 36} className="console-sidebar-mark rounded-lg shadow-sm" />
            {!collapsed ? (
              <div className="min-w-0 flex-1">
                <p className="truncate font-brand text-base font-bold leading-tight text-sidebar-foreground">
                  IoTAPS
                  <span className="font-normal text-sidebar-muted"> Console</span>
                </p>
                <p className="mt-0.5 truncate text-[11px] font-medium text-sidebar-muted">
                  MQTT · dashboards · rules
                </p>
              </div>
            ) : null}
          </NavLink>
        </header>

        <nav className="console-sidebar-nav flex-1 overflow-y-auto" aria-label="Console">
          {groups.map((group, groupIndex) => (
            <div key={group.id} className="console-nav-group">
              {!collapsed ? (
                <p className="console-nav-group-label">{group.label}</p>
              ) : groupIndex > 0 ? (
                <div className="console-nav-group-divider" aria-hidden />
              ) : null}
              <ul className="console-nav-list">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  if (item.soon || !item.to) {
                    return (
                      <li key={navItemKey(item)}>
                        <button
                          type="button"
                          title={item.title || item.label}
                          onClick={() => onNavSoon(item.label)}
                          className={cn("console-nav-item", collapsed && "console-nav-item-collapsed")}
                        >
                          <span className="console-nav-icon">
                            <Icon size={20} weight="regular" />
                          </span>
                          {!collapsed ? (
                            <>
                              <span className="truncate">{item.label}</span>
                              <span className="console-nav-soon">Soon</span>
                            </>
                          ) : null}
                        </button>
                      </li>
                    );
                  }
                  return (
                    <li key={navItemKey(item)}>
                      <NavLink
                        to={item.to}
                        end={item.to === "/get-started"}
                        title={item.title || item.label}
                        className={({ isActive }) =>
                          cn(
                            "console-nav-item",
                            collapsed && "console-nav-item-collapsed",
                            isActive && "console-nav-item-active"
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <span className={cn("console-nav-icon", isActive && "console-nav-icon-active")}>
                              <Icon size={20} weight={isActive ? "duotone" : "regular"} />
                            </span>
                            {!collapsed ? <span className="truncate">{item.label}</span> : null}
                          </>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <footer className="console-sidebar-footer">
          <button
            type="button"
            onClick={onToggleCollapsed}
            className={cn(
              "console-nav-collapse",
              collapsed && "console-nav-collapse-collapsed"
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <CaretDoubleRight size={18} weight="bold" /> : <CaretDoubleLeft size={18} weight="bold" />}
            {!collapsed ? <span>Collapse sidebar</span> : null}
          </button>
        </footer>
      </div>
    </aside>
  );
}
