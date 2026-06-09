import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, FloppyDisk, CircleNotch, Warning } from "@phosphor-icons/react";
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
import { validateFlow, toFlow } from "@/lib/ruleGraph";

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

  const handleGraphChange = useCallback((graph) => {
    graphRef.current = graph;
  }, []);

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
      // Reload so the canvas reflects the canonical server-issued node ids.
      dispatch(fetchRule(current.rule.id));
    } else {
      toast.error(action.payload?.message || "Failed to save rule");
    }
  }, [dispatch, current, name, enabled]);

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
    <section className="mx-auto max-w-6xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" aria-label="Back to rules" onClick={() => navigate("/rules")}>
            <ArrowLeft size={16} />
          </Button>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Rule name"
            className="h-9 w-64 font-medium"
          />
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            Active
            <Switch
              checked={enabled}
              onChange={setEnabled}
              aria-label="Rule active"
            />
          </label>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <CircleNotch size={16} className="animate-spin" /> : <FloppyDisk size={16} />}
            Save
          </Button>
        </div>
      </header>

      {problems.length > 0 ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          <Warning size={18} className="mt-0.5 shrink-0" />
          <ul className="space-y-0.5">
            {problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <RuleEditor
        nodes={initial.nodes}
        edges={initial.edges}
        onChange={handleGraphChange}
      />
    </section>
  );
}
