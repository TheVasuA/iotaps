import { Link } from "react-router-dom";
import {
  List,
  Plus,
  Headset,
  Broadcast,
  ShieldCheck,
  Cpu,
} from "@phosphor-icons/react";
import { useAppSelector } from "@/store/hooks";
import { selectUser } from "@/store/authSlice";
import NotificationCenter from "@/components/notifications/NotificationCenter";
import ConsoleProfileMenu from "@/components/console/ConsoleProfileMenu";
import { ACCOUNT_COMPANY } from "@/lib/accountTypes";

function orgShortId(user) {
  if (!user?.org_id) return "—";
  return String(user.org_id).replace(/-/g, "").slice(-6).toUpperCase();
}

function orgName(user) {
  return String(user?.organization_name || user?.company_name || "").trim();
}

function accountTypeLabel(type) {
  if (type === ACCOUNT_COMPANY) return "Company";
  if (type === "student") return "Student";
  return "Individual";
}

function MessageStat({ used = 0, limit = 100_000 }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const label = limit >= 1000 ? `${(limit / 1000).toFixed(0)}k` : String(limit);

  return (
    <div className="console-bar-stat hidden xl:flex" title="Messages this period">
      <div className="leading-tight">
        <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Messages</p>
        <p className="text-xs font-semibold tabular-nums text-foreground">
          {used.toLocaleString()}
          <span className="font-normal text-muted-foreground"> / {label}</span>
        </p>
      </div>
      <div className="console-bar-stat-track" aria-hidden>
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function ConsoleTopBar({ onOpenMenu, pageTitle, consoleHome, adminMode }) {
  const user = useAppSelector(selectUser);
  const contextLabel = adminMode
    ? pageTitle || "Platform admin"
    : consoleHome
      ? "Get started"
      : pageTitle || "Console";

  return (
    <header className="iotaps-console-bar">
      <div className="iotaps-console-bar-shine" aria-hidden />
      <div className="iotaps-console-bar-inner">
        <div className="console-bar-leading">
          {onOpenMenu ? (
            <button
              type="button"
              className="console-bar-icon-btn md:hidden"
              aria-label="Open navigation"
              onClick={onOpenMenu}
            >
              <List size={20} weight="bold" />
            </button>
          ) : null}

          {adminMode ? (
            <div className="console-bar-admin-badge">
              <ShieldCheck size={22} weight="duotone" className="text-primary" />
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Super admin
                </p>
                <p className="text-sm font-bold text-foreground">{contextLabel}</p>
              </div>
            </div>
          ) : (
            <div className="console-bar-title-wrap">
              <h1 className="console-bar-title">{contextLabel}</h1>
              <p className="console-bar-eyebrow">
                {consoleHome ? "Workspace hub" : "Console"}
              </p>
            </div>
          )}
        </div>

        {!adminMode && orgName(user) ? (
          <div
            className="console-bar-workspace hidden min-w-0 lg:flex"
            title={`${orgName(user)} · ${orgShortId(user)}`}
          >
            <span className="console-bar-workspace-avatar">{orgName(user).charAt(0).toUpperCase()}</span>
            <span className="console-bar-workspace-name truncate">{orgName(user)}</span>
            <span className="console-bar-workspace-type">{accountTypeLabel(user?.account_type)}</span>
          </div>
        ) : null}

        <div className="min-w-0 flex-1" aria-hidden />

        <div className="console-bar-trailing">
          {!adminMode ? <MessageStat /> : null}

          {!adminMode ? (
            <div className="console-bar-quick hidden sm:flex">
              <Link to="/devices" className="console-bar-quick-btn" title="Add device">
                <Plus size={17} weight="bold" />
                <span className="hidden md:inline">Device</span>
              </Link>
              <Link to="/explorer" className="console-bar-quick-btn" title="MQTT explorer">
                <Broadcast size={17} weight="duotone" />
                <span className="hidden md:inline">Live</span>
              </Link>
              <Link to="/support" className="console-bar-quick-btn" title="Support">
                <Headset size={17} />
                <span className="hidden md:inline">Help</span>
              </Link>
            </div>
          ) : (
            <Link to="/get-started" className="console-bar-quick-btn hidden sm:inline-flex">
              <Cpu size={17} />
              <span>Exit to console</span>
            </Link>
          )}

          <div className="console-bar-divider hidden sm:block" aria-hidden />

          <NotificationCenter triggerClassName="console-bar-icon-btn" />
          <ConsoleProfileMenu />
        </div>
      </div>
    </header>
  );
}
