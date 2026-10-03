import { useEffect, useRef, useState } from "react";
import {
  Buildings,
  Copy,
  DotsThree,
  Funnel,
  House,
  PencilSimple,
  Trash,
  User,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { DASHBOARD_TIME_RANGES } from "@/lib/widgets";

const VIEW_RANGES = DASHBOARD_TIME_RANGES.filter((range) => range.id !== "all");

const RANGE_DOT = {
  "1d": "#f5a524",
  "1w": "#3b82f6",
  "1mo": "#22a06b",
  "3mo": "#8b5cf6",
  "1y": "#ef5da8",
};

/** Saved-dashboard view: title, options menu, range chips, organization, filter. */
export default function DashboardViewToolbar({
  title,
  onEdit,
  onDuplicate,
  onManageAccess,
  onSetHomepage,
  onClearHomepage,
  isHomepage,
  onDelete,
  timeRange,
  onTimeRangeChange,
  orgLabel,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onPointer = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    const onKey = (event) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const run = (action) => {
    setMenuOpen(false);
    action?.();
  };

  return (
    <header className="dash-view-toolbar">
      <div className="flex items-center justify-between gap-3">
        <h1 className="dash-view-title">{title || "Dashboard"}</h1>
        <div className="dash-view-options" ref={menuRef}>
          <button
            type="button"
            className="dash-view-options-btn"
            aria-label="Dashboard options"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <DotsThree size={20} weight="bold" />
          </button>
          {menuOpen ? (
            <ul className="dash-view-menu" role="menu">
              <li role="none">
                <button type="button" role="menuitem" className="dash-view-menu-item" onClick={() => run(onEdit)}>
                  <PencilSimple size={18} />
                  Edit Dashboard
                </button>
              </li>
              <li role="none">
                <button type="button" role="menuitem" className="dash-view-menu-item" onClick={() => run(onDuplicate)}>
                  <Copy size={18} />
                  Duplicate Dashboard
                </button>
              </li>
              <li role="none">
                <button type="button" role="menuitem" className="dash-view-menu-item" onClick={() => run(onManageAccess)}>
                  <User size={18} />
                  Manage Access
                </button>
              </li>
              <li role="none">
                {isHomepage ? (
                  <button type="button" role="menuitem" className="dash-view-menu-item" onClick={() => run(onClearHomepage)}>
                    <House size={18} />
                    Do not use as Homepage
                  </button>
                ) : (
                  <button type="button" role="menuitem" className="dash-view-menu-item" onClick={() => run(onSetHomepage)}>
                    <House size={18} />
                    Set as Homepage
                  </button>
                )}
              </li>
              <li role="none">
                <button
                  type="button"
                  role="menuitem"
                  className="dash-view-menu-item dash-view-menu-item-danger"
                  onClick={() => run(onDelete)}
                >
                  <Trash size={18} />
                  Delete Dashboard
                </button>
              </li>
            </ul>
          ) : null}
        </div>
      </div>
      <div className="dash-view-row">
        <div className="dash-time-range" role="group" aria-label="Time range">
          {VIEW_RANGES.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={cn("dash-time-chip", timeRange === id && "dash-time-chip-active")}
              onClick={() => onTimeRangeChange?.(id)}
            >
              <span className="dash-time-dot" style={{ background: RANGE_DOT[id] }} aria-hidden />
              {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="dash-filter-chip">
            <Buildings size={14} />
            {orgLabel || "My organization"}
          </span>
          <button type="button" className="dash-filter-chip" aria-label="Filter">
            <Funnel size={14} />
            Filter
          </button>
        </div>
      </div>
    </header>
  );
}
