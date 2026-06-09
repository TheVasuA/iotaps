import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { GearSix, Trash } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { nodeMeta, describeNode } from "@/lib/ruleGraph";

// Custom React Flow node for the visual rule editor (Task 10.5, Req 10.1).
// Renders a trigger/condition/action/delay card with the appropriate
// connection handles (trigger has only an output, action only an input) and a
// one-line config summary. Settings/delete affordances are surfaced via
// callbacks passed through `data` so the node stays presentational.
function RuleNodeComponent({ id, data, selected }) {
  const meta = nodeMeta(data?.nodeType);
  const label = meta?.label || data?.nodeType || "Node";
  const summary = describeNode(data?.nodeType, data?.config || {});

  return (
    <div
      className={cn(
        "min-w-[168px] rounded-lg border-2 bg-card text-card-foreground shadow-sm",
        meta?.accent || "border-border",
        selected && "ring-2 ring-ring ring-offset-1 ring-offset-background"
      )}
    >
      {meta?.hasInput ? (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-2.5 !w-2.5 !border-2 !border-background !bg-muted-foreground"
        />
      ) : null}

      <div className="flex items-center justify-between gap-2 px-3 pt-2">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            meta?.badge || "bg-muted text-muted-foreground"
          )}
        >
          {label}
        </span>
        {!data?.readOnly ? (
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              aria-label={`Configure ${label}`}
              title="Configure"
              className="nodrag inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={(e) => {
                e.stopPropagation();
                data?.onConfigure?.(id);
              }}
            >
              <GearSix size={14} />
            </button>
            <button
              type="button"
              aria-label={`Delete ${label}`}
              title="Delete"
              className="nodrag inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                data?.onDelete?.(id);
              }}
            >
              <Trash size={14} />
            </button>
          </div>
        ) : null}
      </div>

      <div className="px-3 pb-2.5 pt-1">
        <p className="truncate text-xs text-muted-foreground" title={summary}>
          {summary || "—"}
        </p>
      </div>

      {meta?.hasOutput ? (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-2.5 !w-2.5 !border-2 !border-background !bg-muted-foreground"
        />
      ) : null}
    </div>
  );
}

export default memo(RuleNodeComponent);
