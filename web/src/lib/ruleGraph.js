// Pure helpers that translate between the backend rule-graph shape and the
// React Flow graph shape used by the visual editor (Task 10.5, Req 10.1, 10.5).
//
// Backend shape (app/api/v1/rules.py):
//   node = { id, node_type, config, position: { x, y } }
//   edge = { id, from_node_id, to_node_id }            (GET response)
//   edge = { from, to }                                (POST/PATCH request, refs node ids)
//
// React Flow shape (@xyflow/react):
//   node = { id, type, position: { x, y }, data: { config, ... } }
//   edge = { id, source, target }
//
// Keeping these as side-effect-free functions makes the round-trip
// (backend -> React Flow -> backend) directly testable without rendering.

// The four node kinds the rule engine understands
// (design.md "rule_nodes": trigger/condition/action/delay).
export const NODE_TYPES = ["trigger", "condition", "action", "delay"];

// Catalog metadata used by the palette and node rendering. The accent colours
// are plain Tailwind class fragments so nodes read clearly on the canvas.
const NODE_CATALOG = {
  trigger: {
    label: "Trigger",
    description: "Fires when telemetry for a metric arrives.",
    accent: "border-emerald-500",
    badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    hasInput: false,
    hasOutput: true,
    defaultConfig: () => ({ metric: "temp" }),
  },
  condition: {
    label: "Condition",
    description: "Continues only when the comparison holds.",
    accent: "border-amber-500",
    badge: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    hasInput: true,
    hasOutput: true,
    defaultConfig: () => ({ op: ">", value: 0 }),
  },
  delay: {
    label: "Delay",
    description: "Waits before continuing the chain.",
    accent: "border-sky-500",
    badge: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
    hasInput: true,
    hasOutput: true,
    defaultConfig: () => ({ seconds: 60 }),
  },
  action: {
    label: "Action",
    description: "Notifies, sends a command, or calls a webhook.",
    accent: "border-fuchsia-500",
    badge: "bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-400",
    hasInput: true,
    hasOutput: false,
    defaultConfig: () => ({ type: "notify", message: "Alert" }),
  },
};

/** Whether `type` is one of the four known rule node kinds. */
export function isNodeType(type) {
  return Object.prototype.hasOwnProperty.call(NODE_CATALOG, type);
}

/** Return catalog metadata for a node kind (or null when unknown). */
export function nodeMeta(type) {
  return NODE_CATALOG[type] || null;
}

/** A fresh default config object for a node kind. */
export function defaultConfigFor(type) {
  const meta = NODE_CATALOG[type];
  return meta ? meta.defaultConfig() : {};
}

/**
 * Convert a backend rule graph ({nodes, edges} from GET /rules/{id}) into the
 * React Flow `{ nodes, edges }` shape. Positions fall back to a readable
 * left-to-right layout when the stored node has no position.
 */
export function toFlow(nodes = [], edges = []) {
  const flowNodes = nodes.map((n, index) => {
    const pos = n.position && typeof n.position === "object" ? n.position : {};
    const x = Number.isFinite(pos.x) ? pos.x : index * 220;
    const y = Number.isFinite(pos.y) ? pos.y : 80;
    return {
      id: String(n.id),
      type: "rule",
      position: { x, y },
      data: {
        nodeType: n.node_type,
        config: n.config && typeof n.config === "object" ? { ...n.config } : {},
      },
    };
  });

  const flowEdges = edges.map((e, index) => ({
    id: e.id != null ? String(e.id) : `e${index}`,
    source: String(e.from_node_id),
    target: String(e.to_node_id),
  }));

  return { nodes: flowNodes, edges: flowEdges };
}

/**
 * Convert a React Flow `{ nodes, edges }` graph into the backend create/patch
 * payload ({ nodes:[{id,node_type,config,position}], edges:[{from,to}] }).
 * Node ids are preserved so edges line up; the backend re-issues canonical ids.
 */
export function fromFlow(flowNodes = [], flowEdges = []) {
  const nodes = flowNodes.map((n) => ({
    id: String(n.id),
    node_type: n.data?.nodeType,
    config: n.data?.config && typeof n.data.config === "object" ? n.data.config : {},
    position: {
      x: Math.round(n.position?.x ?? 0),
      y: Math.round(n.position?.y ?? 0),
    },
  }));

  const edges = flowEdges.map((e) => ({
    from: String(e.source),
    to: String(e.target),
  }));

  return { nodes, edges };
}

/**
 * Validate a React Flow graph for the basic structural rules the engine relies
 * on (a linear trigger -> ... chain). Returns an array of human-readable
 * problems; an empty array means the graph is shippable. This mirrors the
 * backend's expectations (one trigger, edges reference known nodes) so the UI
 * can warn before a save round-trip.
 */
export function validateFlow(flowNodes = [], flowEdges = []) {
  const problems = [];
  const triggers = flowNodes.filter((n) => n.data?.nodeType === "trigger");
  if (flowNodes.length === 0) {
    problems.push("Add at least a trigger node to start the chain.");
  }
  if (triggers.length === 0 && flowNodes.length > 0) {
    problems.push("A rule needs exactly one trigger node.");
  }
  if (triggers.length > 1) {
    problems.push("A rule can have only one trigger node.");
  }
  for (const n of flowNodes) {
    if (!isNodeType(n.data?.nodeType)) {
      problems.push(`Node ${n.id} has an unknown type.`);
    }
  }
  const ids = new Set(flowNodes.map((n) => String(n.id)));
  for (const e of flowEdges) {
    if (!ids.has(String(e.source)) || !ids.has(String(e.target))) {
      problems.push("An edge references a node that no longer exists.");
      break;
    }
  }
  return problems;
}

/**
 * Produce a fresh, unique node id for newly-added React Flow nodes. Kept here
 * (rather than relying on a global counter) so the editor stays deterministic
 * and the helper is testable.
 */
export function makeNodeId(existingIds = []) {
  const used = new Set(existingIds.map(String));
  let i = 1;
  // crypto.randomUUID would also work, but a short readable id eases debugging.
  while (used.has(`n${i}`)) i += 1;
  return `n${i}`;
}

/** A short one-line summary of a node's config for compact display. */
export function describeNode(nodeType, config = {}) {
  switch (nodeType) {
    case "trigger":
      return config.metric ? `metric: ${config.metric}` : "any telemetry";
    case "condition":
      return `${config.metric ? `${config.metric} ` : ""}${config.op ?? "?"} ${config.value ?? "?"}`;
    case "delay": {
      const s = Number(config.seconds);
      return Number.isFinite(s) ? `wait ${s}s` : "wait";
    }
    case "action":
      if (config.type === "command") {
        return `command ${config.command ?? ""}${config.value != null ? `=${config.value}` : ""}`.trim();
      }
      if (config.type === "webhook") return "call webhook";
      return config.message ? `notify: ${config.message}` : "notify";
    default:
      return "";
  }
}
