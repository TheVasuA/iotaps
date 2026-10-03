import { Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

/** Empty dashboards — left copy on a dot canvas, ghost widgets on the right. */
export default function DashboardEmptyState({ onCreate }) {
  return (
    <div className="dash-studio">
      <section className="dash-studio-copy">
        <p className="dash-studio-kicker">No boards yet</p>
        <h1 className="dash-studio-title">Dashboards</h1>
        <p className="dash-studio-desc">
          Create dashboards to monitor key metrics and control devices at a glance.
        </p>
        <Button type="button" size="lg" className="dash-studio-cta font-semibold" onClick={onCreate}>
          <Plus size={18} weight="bold" className="mr-2" />
          Create Dashboard
        </Button>
      </section>

      <div className="dash-studio-stage" aria-hidden>
        <div className="dash-studio-tile dash-studio-tile-chart">
          <span className="dash-studio-tile-label">Telemetry</span>
          <svg viewBox="0 0 160 56" className="dash-studio-spark">
            <polyline
              points="0,40 24,34 40,38 58,18 78,26 100,10 124,22 160,8"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <div className="dash-studio-tile dash-studio-tile-gauge">
          <span className="dash-studio-tile-label">Gauge</span>
          <div className="dash-studio-arc" />
          <strong>72</strong>
        </div>
        <div className="dash-studio-tile dash-studio-tile-switch">
          <span className="dash-studio-tile-label">Control</span>
          <span className="dash-studio-switch" />
        </div>
        <div className="dash-studio-tile dash-studio-tile-stat">
          <span className="dash-studio-tile-label">Online</span>
          <strong>12</strong>
          <em>devices</em>
        </div>
      </div>
    </div>
  );
}
