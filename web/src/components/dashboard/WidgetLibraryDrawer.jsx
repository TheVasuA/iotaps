import {
  ChartLine,
  ChartBar,
  Gauge,
  Numpad,
  MapPin,
  ToggleLeft,
  Sliders,
  Warning,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { widgetsByCategory, widgetMeta } from "@/lib/widgets";

const ICONS = {
  line: ChartLine,
  bar: ChartBar,
  gauge: Gauge,
  value: Numpad,
  map: MapPin,
  toggle: ToggleLeft,
  slider: Sliders,
  alert_badge: Warning,
};

const SWATCH = {
  line: "bg-blue-500",
  bar: "bg-violet-500",
  gauge: "bg-emerald-500",
  value: "bg-sky-500",
  map: "bg-amber-500",
  toggle: "bg-orange-500",
  slider: "bg-pink-500",
  alert_badge: "bg-red-500",
};

/** Blynk-style widget library — categories with tap-to-add tiles. */
export default function WidgetLibraryDrawer({ open, onClose, onAdd, className }) {
  const groups = widgetsByCategory();

  if (!open) return null;

  return (
    <aside
      className={cn(
        "flex w-full shrink-0 flex-col border-t border-border bg-card md:w-72 md:border-l md:border-t-0",
        className
      )}
      aria-label="Widget library"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <div>
          <p className="text-sm font-semibold text-foreground">Widget library</p>
          <p className="text-[11px] text-muted-foreground">Tap a tile to add to the canvas</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
          aria-label="Close widget library"
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {groups.map((group) =>
          group.types.length === 0 ? null : (
            <section key={group.id} className="mb-4 last:mb-0">
              <h3 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {group.label}
              </h3>
              <ul className="space-y-1.5">
                {group.types.map((type) => {
                  const meta = widgetMeta(type);
                  const Icon = ICONS[type] || Numpad;
                  return (
                    <li key={type}>
                      <button
                        type="button"
                        onClick={() => onAdd?.(type)}
                        className="flex w-full items-center gap-3 rounded-xl border border-border bg-background p-2.5 text-left transition-all hover:border-primary/50 hover:shadow-md active:scale-[0.99]"
                      >
                        <span
                          className={cn(
                            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white shadow-sm",
                            SWATCH[type] || "bg-primary"
                          )}
                        >
                          <Icon size={22} weight="duotone" />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium leading-tight">
                            {meta?.label || type}
                          </span>
                          <span className="line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                            {meta?.description}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )
        )}
      </div>
    </aside>
  );
}
