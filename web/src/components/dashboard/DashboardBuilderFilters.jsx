import { Database, UsersThree } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { DASHBOARD_TIME_RANGES } from "@/lib/widgets";

const BUILDER_RANGES = DASHBOARD_TIME_RANGES.filter((r) =>
  ["1d", "1w", "1mo", "3mo", "1y"].includes(r.id)
);

/** Scope, access, and default range — same card language as the console. */
export default function DashboardBuilderFilters({
  sourceLabel = "All devices in this workspace",
  onChangeSource,
  timeRange,
  onTimeRangeChange,
  onManageAccess,
}) {

  return (
    <div className="dash-builder-filters">
      <section className="dash-builder-filter">
        <span className="dash-builder-filter-icon">
          <Database size={18} weight="duotone" />
        </span>
        <div className="min-w-0 flex-1">
          <h3>Data source</h3>
          <p>{sourceLabel}</p>
        </div>
        <button type="button" className="dash-builder-filter-btn" onClick={onChangeSource}>
          Change
        </button>
      </section>

      <section className="dash-builder-filter">
        <span className="dash-builder-filter-icon">
          <UsersThree size={18} weight="duotone" />
        </span>
        <div className="min-w-0 flex-1">
          <h3>Access</h3>
          <p>Who can open this dashboard</p>
        </div>
        <button type="button" className="dash-builder-filter-btn" onClick={onManageAccess}>
          Manage
        </button>
      </section>

      <section className="dash-builder-filter dash-builder-filter-range-card">
        <div className="min-w-0">
          <h3>Default date range</h3>
          <p>Will be applied by default</p>
        </div>
        <div className="dash-builder-filter-range" role="group" aria-label="Default date range">
          {BUILDER_RANGES.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={cn(
                "dash-builder-range-chip",
                timeRange === id && "dash-builder-range-chip-active"
              )}
              onClick={() => onTimeRangeChange?.(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
