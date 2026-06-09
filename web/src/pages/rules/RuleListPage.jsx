import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Stack, Trash, PencilSimple, CircleNotch } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchRules,
  fetchTemplates,
  createNewRule,
  saveRule,
  removeRule,
  instantiateTemplate,
  selectRules,
  selectRuleTemplates,
  selectRulesStatus,
  selectRulesError,
} from "@/store/rulesSlice";
import TemplatePickerDialog from "@/components/rules/TemplatePickerDialog";

// Rule list page (Task 10.5, Req 10.1, 10.5). Lists the org's automation rules,
// lets the user toggle a rule active/inactive (the backend enforces the per-plan
// active-rule limit, Req 10.6-10.8), create a blank rule, instantiate one from a
// template, and open the visual editor.
export default function RuleListPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const rules = useAppSelector(selectRules);
  const templates = useAppSelector(selectRuleTemplates);
  const status = useAppSelector(selectRulesStatus);
  const error = useAppSelector(selectRulesError);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  useEffect(() => {
    dispatch(fetchRules());
  }, [dispatch]);

  const openTemplatePicker = useCallback(async () => {
    setPickerOpen(true);
    setTemplatesLoading(true);
    await dispatch(fetchTemplates());
    setTemplatesLoading(false);
  }, [dispatch]);

  const handleCreateBlank = useCallback(async () => {
    const name = window.prompt("New rule name", "My rule");
    if (!name) return;
    // Create disabled so a blank rule never trips the active-rule limit before
    // the user has built its chain; they enable it from the list or editor.
    const action = await dispatch(
      createNewRule({ name, enabled: false, nodes: [], edges: [] })
    );
    if (createNewRule.fulfilled.match(action)) {
      toast.success("Rule created");
      navigate(`/rules/${action.payload.id}`);
    } else {
      toast.error(action.payload?.message || "Failed to create rule");
    }
  }, [dispatch, navigate]);

  const handleInstantiate = useCallback(
    async (templateId) => {
      const action = await dispatch(instantiateTemplate(templateId));
      if (instantiateTemplate.fulfilled.match(action)) {
        toast.success("Rule created from template");
        setPickerOpen(false);
        navigate(`/rules/${action.payload.id}`);
      } else {
        toast.error(action.payload?.message || "Failed to create rule from template");
      }
    },
    [dispatch, navigate]
  );

  const handleToggle = useCallback(
    async (rule) => {
      const action = await dispatch(
        saveRule({ id: rule.id, changes: { enabled: !rule.enabled } })
      );
      if (saveRule.fulfilled.match(action)) {
        toast.success(action.payload.enabled ? "Rule activated" : "Rule deactivated");
      } else {
        // The plan limit (Req 10.6-10.8) surfaces here as a 403 message.
        toast.error(action.payload?.message || "Failed to update rule");
      }
    },
    [dispatch]
  );

  const handleDelete = useCallback(
    async (rule) => {
      if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
      const action = await dispatch(removeRule(rule.id));
      if (removeRule.fulfilled.match(action)) toast.success("Rule deleted");
      else toast.error(action.payload?.message || "Failed to delete rule");
    },
    [dispatch]
  );

  return (
    <section className="mx-auto max-w-5xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-primary">Rules</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={openTemplatePicker}>
            <Stack size={16} />
            From template
          </Button>
          <Button onClick={handleCreateBlank}>
            <Plus size={16} />
            New rule
          </Button>
        </div>
      </header>

      {status === "loading" && rules.length === 0 ? (
        <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
          <CircleNotch size={22} className="animate-spin" />
        </div>
      ) : status === "failed" && rules.length === 0 ? (
        <div className="flex min-h-[40vh] items-center justify-center text-destructive">
          {error || "Failed to load rules"}
        </div>
      ) : rules.length === 0 ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border text-muted-foreground">
          <p>No rules yet.</p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={openTemplatePicker}>
              <Stack size={16} />
              Start from a template
            </Button>
            <Button onClick={handleCreateBlank}>
              <Plus size={16} />
              Create a rule
            </Button>
          </div>
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className="flex items-center justify-between gap-3 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{rule.name}</span>
                  <Badge variant={rule.enabled ? "success" : "muted"}>
                    {rule.enabled ? "Active" : "Inactive"}
                  </Badge>
                  {rule.template_id ? (
                    <Badge variant="outline">Template</Badge>
                  ) : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="hidden sm:inline">Active</span>
                  <Switch
                    checked={rule.enabled}
                    onChange={() => handleToggle(rule)}
                    aria-label={`Toggle ${rule.name}`}
                  />
                </label>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/rules/${rule.id}`)}
                >
                  <PencilSimple size={16} />
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${rule.name}`}
                  onClick={() => handleDelete(rule)}
                >
                  <Trash size={16} />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <TemplatePickerDialog
        open={pickerOpen}
        templates={templates}
        loading={templatesLoading}
        onClose={() => setPickerOpen(false)}
        onInstantiate={handleInstantiate}
      />
    </section>
  );
}
