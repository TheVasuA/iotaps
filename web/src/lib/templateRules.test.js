import { describe, it, expect } from "vitest";
import { graphFromTemplateRulesDef } from "./templateRules.js";

describe("graphFromTemplateRulesDef", () => {
  it("returns null when rules_def is empty", () => {
    expect(graphFromTemplateRulesDef(null)).toBeNull();
    expect(graphFromTemplateRulesDef({ rules: [] })).toBeNull();
  });

  it("maps the first rule graph", () => {
    const graph = graphFromTemplateRulesDef({
      rules: [
        {
          name: "Alert",
          nodes: [{ id: "t", node_type: "trigger", config: { metric: "temp" } }],
          edges: [{ from: "t", to: "a" }],
        },
      ],
    });
    expect(graph.name).toBe("Alert");
    expect(graph.nodes).toHaveLength(1);
    expect(graph.edges[0].from).toBe("t");
  });
});
