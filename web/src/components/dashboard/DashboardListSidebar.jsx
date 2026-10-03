import { Link } from "react-router-dom";
import { Plus, CaretLeft } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export default function DashboardListSidebar({
  dashboards,
  selectedId,
  onSelect,
  onCreate,
  maxDashboards = 10,
}) {
  const atLimit = dashboards.length >= maxDashboards;

  return (
    <aside className="dash-nav-sidebar" aria-label="My dashboards">
      <div className="dash-nav-head">
        <p className="dash-nav-kicker">My dashboards</p>
        <button
          type="button"
          className="dash-nav-add"
          onClick={onCreate}
          disabled={atLimit}
          aria-label="New dashboard"
        >
          <Plus size={16} weight="bold" />
        </button>
      </div>
      <ul className="dash-nav-list">
        {dashboards.map((d) => {
          const active = d.id === selectedId;
          return (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onSelect(d.id)}
                className={cn("dash-nav-item", active && "dash-nav-item-active")}
              >
                <span className="dash-nav-bullet" aria-hidden />
                <span className="truncate">{d.name}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="dash-nav-upgrade">
        <p className="text-sm font-bold text-white">Add more dashboards</p>
        <p className="mt-1 text-xs leading-relaxed text-white/70">
          Create additional dashboards and share them with users in company workspaces.
        </p>
        <Link to="/billing" className="dash-nav-upgrade-btn">
          <CaretLeft size={14} weight="fill" className="rotate-180" />
          Upgrade
        </Link>
      </div>
    </aside>
  );
}
