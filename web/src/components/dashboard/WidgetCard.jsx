import {
  PushPin,
  GearSix,
  TrashSimple,
  DotsSixVertical,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { widgetMeta } from "@/lib/widgets";
import WidgetRenderer from "./WidgetRenderer";

// Color palette for widget tiles (Blynk-style)
const TYPE_COLORS = {
  line: "from-blue-500/10 to-blue-600/5 border-blue-400/40",
  bar: "from-violet-500/10 to-violet-600/5 border-violet-400/40",
  gauge: "from-emerald-500/10 to-emerald-600/5 border-emerald-400/40",
  value: "from-sky-500/10 to-sky-600/5 border-sky-400/40",
  map: "from-amber-500/10 to-amber-600/5 border-amber-400/40",
  toggle: "from-orange-500/10 to-orange-600/5 border-orange-400/40",
  slider: "from-pink-500/10 to-pink-600/5 border-pink-400/40",
  alert_badge: "from-red-500/10 to-red-600/5 border-red-400/40",
  chart: "from-indigo-500/10 to-indigo-600/5 border-indigo-400/40",
};

export default function WidgetCard({
  widget,
  editing,
  onCommand,
  onTogglePin,
  onConfigure,
  onDelete,
  readOnly,
  dragListeners,
}) {
  const meta = widgetMeta(widget.type);
  const title =
    widget.config?.label || widget.config?.title || meta?.label || widget.type || "Widget";
  const colorClass = TYPE_COLORS[widget.type] || TYPE_COLORS.chart;

  return (
    <div
      className={cn(
        "flex h-full flex-col overflow-hidden rounded-xl border bg-gradient-to-br transition-all",
        colorClass,
        editing && "shadow-lg hover:shadow-xl",
        !editing && "shadow-sm hover:shadow-md",
        widget.pinned && "ring-2 ring-primary/40"
      )}
    >
      {/* Header with drag handle */}
      <div
        className={cn(
          "flex items-center justify-between gap-1 px-2 py-1",
          editing && "cursor-grab active:cursor-grabbing"
        )}
        {...(editing && dragListeners ? dragListeners : {})}
      >
        <div className="flex min-w-0 items-center gap-1.5">
          {editing && (
            <DotsSixVertical size={16} weight="bold" className="shrink-0 text-foreground/40" />
          )}
          <span className="truncate text-xs font-semibold uppercase tracking-wide text-foreground/70">
            {title}
          </span>
        </div>

        {/* Actions */}
        {editing && !readOnly && (
          <div className="flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onTogglePin?.(widget)}
              title={widget.pinned ? "Unpin" : "Pin"}
              className={cn(
                "inline-flex h-6 w-6 items-center justify-center rounded-full transition-colors",
                widget.pinned ? "bg-primary/20 text-primary" : "text-foreground/40 hover:bg-foreground/10"
              )}
            >
              <PushPin size={12} weight={widget.pinned ? "fill" : "regular"} />
            </button>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onConfigure?.(widget)}
              title="Settings"
              className="inline-flex h-6 w-6 items-center justify-center rounded-full text-foreground/40 hover:bg-foreground/10 hover:text-foreground"
            >
              <GearSix size={12} />
            </button>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onDelete?.(widget)}
              title="Remove"
              className="inline-flex h-6 w-6 items-center justify-center rounded-full text-foreground/40 hover:bg-red-500/10 hover:text-red-500"
            >
              <TrashSimple size={12} />
            </button>
          </div>
        )}

        {/* View-mode pin indicator */}
        {!editing && widget.pinned && (
          <PushPin size={12} weight="fill" className="shrink-0 text-primary" />
        )}
      </div>

      {/* Widget content */}
      <div className="min-h-0 flex-1 px-1 pb-1">
        <WidgetRenderer widget={widget} onCommand={onCommand} readOnly={readOnly} />
      </div>
    </div>
  );
}
