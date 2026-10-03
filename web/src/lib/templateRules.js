/** Extract the first rule graph from a template `rules_def` payload. */
export function graphFromTemplateRulesDef(rulesDef) {
  const list = rulesDef?.rules;
  if (!Array.isArray(list) || list.length === 0) return null;
  const first = list[0];
  const nodes = (first.nodes || []).map((n, i) => ({
    id: n.id || `n${i}`,
    node_type: n.node_type,
    config: n.config || {},
    position: n.position || { x: 40 + i * 40, y: 40 + i * 20 },
  }));
  const edges = (first.edges || []).map((e, i) => ({
    id: e.id || `e${i}`,
    from: e.from ?? e.from_node_id,
    to: e.to ?? e.to_node_id,
  }));
  return { name: first.name, enabled: first.enabled, nodes, edges };
}
