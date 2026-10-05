import { cn } from "@/lib/utils";

/** Horizontal entity tabs with a soft primary underline. */
export default function EntityTabs({ tabs, active, onChange, className }) {
  return (
    <div
      className={cn(
        "flex gap-1 overflow-x-auto rounded-xl border border-border bg-card px-2 shadow-sm scrollbar-thin",
        className
      )}
      role="tablist"
    >
      {tabs.map((tab) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={cn(
              "shrink-0 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors",
              selected
                ? "bg-primary/10 text-primary shadow-[inset_0_-2px_0_0_hsl(var(--primary))]"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
