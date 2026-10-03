import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, FloppyDisk, CircleNotch, Warning, Stack } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchRule,
  saveRule,
  clearCurrentRule,
  selectCurrentRule,
  selectRulesStatus,
  selectRulesSaving,
  selectRulesError,
} from "@/store/rulesSlice";
import RuleEditor from "@/components/rules/RuleEditor";
import RuleDebugPanel from "@/components/rules/RuleDebugPanel";
import TemplatePickerDialog from "@/components/rules/TemplatePickerDialog";
import { validateFlow, toFlow } from "@/lib/ruleGraph";
import { getTemplate } from "@/lib/rulesApi";
import { graphFromTemplateRulesDef } from "@/lib/templateRules";
import {
  fetchTemplates,
  selectRuleTemplates,
} from "@/store/rulesSlice";
import { useRuleDebugLog } from "@/lib/useRuleDebugLog";

// Visual rule editor page (Task 10.5, Req 10.1). Loads a rule + its React Flow
// graph, hosts the canvas editor, and persists name/enabled/graph changes via
// PATCH /rules/{id}. The backend re-checks the per-plan active-rule limit
// (Req 10.6-10.8) when enabling, surfaced here as a toast.
export default function RuleEditorPage() {
  const { id } = useParams();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const current = useAppSelector(selectCurrentRule);
  const status = useAppSelector(selectRulesStatus);
  const saving = useAppSelector(selectRulesSaving);
  const error = useAppSelector(selectRulesError);

  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(false);
  // Latest backend-shape graph from the editor; kept in a ref so the editor's
  // onChange does not re-render this page on every canvas tick.
  const graphRef = useRef({ nodes: [], edges: [] });
  const [problems, setProblems] = useState([]);
  const {
    logs: debugLogs,
    open: debugOpen,
    appendLog: handleEditorLog,
    clearLogs: clearDebugLogs,
    toggleOpen: toggleDebugOpen,
  } = useRuleDebugLog(id);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const templates = useAppSelector(selectRuleTemplates);

  useEffect(() => {
    if (id) dispatch(fetchRule(id));
    return () => dispatch(clearCurrentRule());
  }, [dispatch, id]);

  useEffect(() => {
    if (current?.rule) {
      setName(current.rule.name);
      setEnabled(current.rule.enabled);
    }
  }, [current]);

  const openedRuleRef = useRef(null);
  useEffect(() => {
    if (!current?.rule || openedRuleRef.current === current.rule.id) return;
    openedRuleRef.current = current.rule.id;
    handleEditorLog({
      level: "info",
      message: `Opened rule “${current.rule.name}”`,
    });
  }, [current?.rule, handleEditorLog]);

  const handleGraphChange = useCallback((graph) => {
    graphRef.current = graph;
  }, []);

  const openTemplateImport = useCallback(async () => {
    setTemplateOpen(true);
    setTemplatesLoading(true);
    await dispatch(fetchTemplates());
    setTemplatesLoading(false);
  }, [dispatch]);

  const handleImportTemplate = useCallback(
    async (templateId) => {
      if (!current?.rule) return;
      try {
        const tpl = await getTemplate(templateId);
        const graph = graphFromTemplateRulesDef(tpl.rules_def);
        if (!graph) {
          toast.error("This template has no rule graph to import");
          return;
        }
        if (
          !window.confirm(
            "Replace the current flow with this template? Unsaved changes will be lost."
          )
        ) {
          return;
        }
        graphRef.current = { nodes: graph.nodes, edges: graph.edges };
        const action = await dispatch(
          saveRule({
            id: current.rule.id,
            changes: { nodes: graph.nodes, edges: graph.edges },
          })
        );
        if (saveRule.fulfilled.match(action)) {
          toast.success("Template imported into flow");
          setTemplateOpen(false);
          handleEditorLog({ ts: Date.now(), level: "success", message: `Imported template: ${tpl.name}` });
          dispatch(fetchRule(current.rule.id));
        } else {
          toast.error(action.payload?.message || "Import failed");
        }
      } catch (err) {
        toast.error(err?.message || "Failed to load template");
      }
    },
    [current, dispatch, handleEditorLog]
  );

  const handleSave = useCallback(async () => {
    if (!current?.rule) return;
    const { nodes, edges } = graphRef.current;
    // Validate against the editor's React Flow view so messages match the canvas.
    const flow = toFlow(
      nodes.map((n) => ({ ...n, position: n.position })),
      edges.map((e) => ({ from_node_id: e.from, to_node_id: e.to }))
    );
    const found = validateFlow(flow.nodes, flow.edges);
    setProblems(found);
    if (enabled && found.length > 0) {
      toast.error("Fix the highlighted problems before activating this rule.");
      return;
    }
    const action = await dispatch(
      saveRule({
        id: current.rule.id,
        changes: { name: name.trim() || current.rule.name, enabled, nodes, edges },
      })
    );
    if (saveRule.fulfilled.match(action)) {
      toast.success("Rule saved");
      handleEditorLog({
        ts: Date.now(),
        level: enabled ? "success" : "info",
        message: enabled ? "Flow deployed (rule active)" : "Flow saved (inactive)",
      });
      found.forEach((p) =>
        handleEditorLog({ ts: Date.now(), level: "warn", message: p })
      );
      dispatch(fetchRule(current.rule.id));
    } else {
      toast.error(action.payload?.message || "Failed to save rule");
    }
  }, [dispatch, current, name, enabled, handleEditorLog]);

  const initial = useMemo(
    () => ({ nodes: current?.nodes || [], edges: current?.edges || [] }),
    [current]
  );

  if (status === "loading" && !current) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground">
        <CircleNotch size={22} className="animate-spin" />
      </div>
    );
  }

  if (!current?.rule) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <Button variant="outline" size="sm" onClick={() => navigate("/rules")}>
          <ArrowLeft size={16} />
          Back to rules
        </Button>
        <p className="text-destructive">{error || "Rule not found."}</p>
      </div>
    );
  }

  return (
    <section className="flex min-h-[calc(100vh-3.5rem)] flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/30 px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="outline" size="icon" aria-label="Back to rules" onClick={() => navigate("/rules")}>
            <ArrowLeft size={16} />
          </Button>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Rule name"
            className="h-9 max-w-xs font-medium md:max-w-md"
          />
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Node-RED style flow · drag wires between nodes
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={openTemplateImport}>
            <Stack size={14} />
            Import template
          </Button>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Deploy
            <Switch
              checked={enabled}
              onChange={setEnabled}
              aria-label="Rule active"
            />
          </label>
          <Button onClick={handleSave} disabled={saving} className="min-w-[5.5rem]">
            {saving ? <CircleNotch size={16} className="animate-spin" /> : <FloppyDisk size={16} />}
            Save flow
          </Button>
        </div>
      </header>

      {problems.length > 0 ? (
        <div className="mx-4 mt-2 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          <Warning size={18} className="mt-0.5 shrink-0" />
          <ul className="space-y-0.5">
            {problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col">
        <RuleEditor
          nodes={initial.nodes}
          edges={initial.edges}
          onChange={handleGraphChange}
          onLog={handleEditorLog}
        />
        <RuleDebugPanel
          logs={debugLogs}
          open={debugOpen}
          onToggle={toggleDebugOpen}
          onClear={clearDebugLogs}
        />
      </div>

      <TemplatePickerDialog
        mode="import"
        open={templateOpen}
        templates={templates}
        loading={templatesLoading}
        onClose={() => setTemplateOpen(false)}
        onInstantiate={handleImportTemplate}
      />
    </section>
  );
}
