import { cn } from "@/lib/utils";
import { Terminal } from "@phosphor-icons/react";

/** Node-RED-style debug sidebar for the rule editor. */
export default function RuleDebugPanel({ logs, open, onToggle, onClear }) {
  if (!open) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-center gap-2 border-t border-border bg-muted/40 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
      >
        <Terminal size={14} />
        Show debug
      </button>
    );
  }

  return (
    <div className="flex max-h-48 min-h-[8rem] flex-col border-t border-border bg-zinc-950 text-zinc-100 md:max-h-56">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5">
        <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          <Terminal size={14} />
          Debug
        </span>
        <div className="flex items-center gap-3">
          {onClear ? (
            <button
              type="button"
              onClick={onClear}
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              Clear
            </button>
          ) : null}
          <button type="button" onClick={onToggle} className="text-xs text-zinc-500 hover:text-zinc-300">
            Hide
          </button>
        </div>
      </div>
      <ol className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-relaxed">
        {logs.length === 0 ? (
          <li className="text-zinc-500">Connect nodes or deploy to see activity…</li>
        ) : (
          logs.map((log, i) => (
            <li
              key={`${log.ts}-${i}`}
              className={cn(
                "border-b border-zinc-900/80 py-1 last:border-0",
                log.level === "error" && "text-red-400",
                log.level === "warn" && "text-amber-400",
                log.level === "success" && "text-emerald-400",
                log.level === "info" && "text-zinc-300"
              )}
            >
              <span className="text-zinc-600">
                {new Date(log.ts).toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}{" "}
              </span>
              {log.message}
            </li>
          ))
        )}
      </ol>
    </div>
  );
}
