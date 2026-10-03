import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useMatches } from "react-router-dom";
import { cn } from "@/lib/utils";
// Lazy so framer-motion stays out of the entry chunk; the popup is non-critical
// chrome and can pop in after the shell renders.
const WhatsNewPopup = lazy(() => import("./changelog/WhatsNewPopup"));
import useNotifications from "@/lib/useNotifications";
import { useAppSelector } from "@/store/hooks";
import { selectRole } from "@/store/authSlice";
import { titleForPathname } from "@/lib/appNav";
import { adminTitleForPath } from "@/lib/adminNav";
import ConsoleSidebar from "@/components/console/ConsoleSidebar";
import ConsoleTopBar from "@/components/console/ConsoleTopBar";

const SIDEBAR_KEY = "iotaps.sidebar.collapsed";

export default function AppLayout() {
  const location = useLocation();
  const matches = useMatches();
  const role = useAppSelector(selectRole);

  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useNotifications();

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const fullBleed = useMemo(
    () => matches.some((m) => m.handle?.fullBleed),
    [matches]
  );

  const consoleHome = useMemo(
    () => matches.some((m) => m.handle?.consoleHome),
    [matches]
  );

  const adminMode = location.pathname.startsWith("/admin");

  const pageTitle = adminMode
    ? adminTitleForPath(location.pathname)
    : consoleHome
      ? null
      : titleForPathname(location.pathname);

  const user = useAppSelector((s) => s.auth.user);

  const sidebarProps = {
    user,
    role,
    collapsed,
    onToggleCollapsed: () => setCollapsed((c) => !c),
  };

  return (
    <div
      className={cn(
        "console-shell flex h-dvh overflow-hidden text-foreground",
        adminMode ? "bg-background" : "bg-[hsl(var(--muted)/0.45)]"
      )}
    >
      {!adminMode ? (
        <ConsoleSidebar
          {...sidebarProps}
          className={cn("hidden shrink-0 md:flex", collapsed ? "w-[4.5rem]" : "w-[17rem]")}
        />
      ) : null}

      {!adminMode && mobileOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      {!adminMode ? (
        <ConsoleSidebar
          {...sidebarProps}
          collapsed={false}
          className={cn(
            "fixed inset-y-0 left-0 z-50 w-[17rem] shadow-2xl transition-transform md:hidden",
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          )}
        />
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <ConsoleTopBar
          onOpenMenu={adminMode ? undefined : () => setMobileOpen(true)}
          pageTitle={pageTitle}
          consoleHome={consoleHome}
          adminMode={adminMode}
        />

        <main
          className={cn(
            "flex-1 min-h-0 overflow-auto",
            adminMode || fullBleed ? "p-0" : consoleHome ? "p-0" : "px-4 pb-6 pt-2 sm:px-6"
          )}
        >
          <Outlet />
        </main>
      </div>

      <Suspense fallback={null}>
        <WhatsNewPopup />
      </Suspense>
    </div>
  );
}
