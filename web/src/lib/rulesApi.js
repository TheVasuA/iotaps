import apiClient from "@/lib/apiClient";

// Rules & Templates API surface (design.md "Rules & Templates", Req 10, 11).
// Each function maps 1:1 to a backend endpoint under /api/v1 and returns the
// parsed body. Token handling and tenant scoping are applied by the shared
// apiClient and the backend middleware respectively.
//
// Wire shapes (see app/api/v1/rules.py):
//   GET    /rules                 -> [rule]                         (rule = {id, org_id, name, enabled, template_id})
//   POST   /rules                 {name, enabled, nodes, edges, template_id?} -> { rule }
//   GET    /rules/{id}            -> { rule, nodes, edges }
//                                    node = {id, node_type, config, position}
//                                    edge = {id, from_node_id, to_node_id}
//   PATCH  /rules/{id}            {name?, enabled?, nodes?, edges?} -> { rule }
//   DELETE /rules/{id}            -> 204
//   POST   /rules/from-template   {template_id} -> { rule }
//   GET    /templates             ?category -> [template]
//
// On create/patch the graph is sent with client-supplied node ids and edges
// that reference them via {from, to}; the backend replaces the stored graph.

/** List rules in the caller's organization. */
export async function listRules() {
  const { data } = await apiClient.get("/rules");
  return data; // [rule]
}

/** Fetch a rule and its React Flow graph. */
export async function getRule(id) {
  const { data } = await apiClient.get(`/rules/${id}`);
  return data; // { rule, nodes, edges }
}

/** Create a rule from a React Flow graph (nodes + edges). */
export async function createRule({ name, enabled = true, nodes, edges, templateId } = {}) {
  const body = {
    name,
    enabled,
    nodes: nodes || [],
    edges: edges || [],
  };
  if (templateId) body.template_id = templateId;
  const { data } = await apiClient.post("/rules", body);
  return data.rule; // { rule } -> rule
}

/**
 * Update a rule. Only the provided keys are sent so a rename does not clobber
 * the graph and vice versa. Supplying `nodes`/`edges` replaces the stored graph.
 */
export async function updateRule(id, changes = {}) {
  const body = {};
  if ("name" in changes) body.name = changes.name;
  if ("enabled" in changes) body.enabled = changes.enabled;
  if ("nodes" in changes) body.nodes = changes.nodes;
  if ("edges" in changes) body.edges = changes.edges;
  const { data } = await apiClient.patch(`/rules/${id}`, body);
  return data.rule;
}

/** Delete a rule and its graph (Req 10.1). */
export async function deleteRule(id) {
  await apiClient.delete(`/rules/${id}`);
}

/** Instantiate a new rule pre-populated from a template (Req 10.5). */
export async function createRuleFromTemplate(templateId) {
  const { data } = await apiClient.post("/rules/from-template", {
    template_id: templateId,
  });
  return data.rule; // { rule } -> rule
}

/** List the global template catalog, optionally filtered by category (Req 11). */
export async function listTemplates(category) {
  const params = {};
  if (category) params.category = category;
  const { data } = await apiClient.get("/templates", { params });
  return data; // [template]
}
