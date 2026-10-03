import { cn } from "@/lib/utils";

/** ThingsBoard-style horizontal entity tabs. */
export default function EntityTabs({ tabs, active, onChange, className }) {
  return (
    <div
      className={cn(
        "flex gap-0 overflow-x-auto border-b border-border scrollbar-thin",
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
              "shrink-0 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
              selected
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
