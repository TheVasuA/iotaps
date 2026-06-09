import { useEffect, useState } from "react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Rule-from-template instantiation UI (Task 10.5, Req 10.5). Lists the global
// template catalog (loaded by the parent into `templates`), lets the user pick
// one, and reports the choice via `onInstantiate(templateId)`. The parent calls
// POST /rules/from-template and refreshes the rule list.
export default function TemplatePickerDialog({
  open,
  templates,
  loading,
  onClose,
  onInstantiate,
}) {
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    if (open) setSelectedId(null);
  }, [open]);

  const grouped = groupByCategory(templates || []);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create rule from template"
      description="Pick a pre-built template to instantiate a new rule."
      className="max-w-2xl"
    >
      <DialogBody className="max-h-[60vh] space-y-5 overflow-y-auto">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading templates…</p>
        ) : (templates || []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No templates are available yet.
          </p>
        ) : (
          Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {category}
              </h3>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {items.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(t.id)}
                      className={cn(
                        "flex w-full flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors hover:bg-accent",
                        selectedId === t.id
                          ? "border-primary ring-2 ring-ring"
                          : "border-border"
                      )}
                    >
                      <span className="text-sm font-medium">{t.name}</span>
                      {t.rules_def ? (
                        <span className="text-xs text-muted-foreground">
                          {countRules(t.rules_def)} rule(s) included
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </DialogBody>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          disabled={!selectedId}
          onClick={() => selectedId && onInstantiate?.(selectedId)}
        >
          Create rule
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function groupByCategory(templates) {
  return templates.reduce((acc, t) => {
    const key = t.category || "Other";
    (acc[key] ||= []).push(t);
    return acc;
  }, {});
}

function countRules(rulesDef) {
  if (Array.isArray(rulesDef)) return rulesDef.length;
  if (rulesDef && Array.isArray(rulesDef.rules)) return rulesDef.rules.length;
  return 1;
}
