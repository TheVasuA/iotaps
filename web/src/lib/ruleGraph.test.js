// Unit + property tests for the rule-graph mapping helpers (Task 10.5,
// Req 10.1, 10.5). These functions are pure (no React Flow runtime), so they
// are exercised directly. The key property is the round-trip between the
// backend graph shape and the React Flow shape.

import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  NODE_TYPES,
  isNodeType,
  nodeMeta,
  defaultConfigFor,
  toFlow,
  fromFlow,
  validateFlow,
  makeNodeId,
  describeNode,
} from "./ruleGraph.js";

describe("node catalog", () => {
  it("exposes the 4 design node kinds", () => {
    expect(NODE_TYPES).toEqual(["trigger", "condition", "action", "delay"]);
  });

  it("trigger has no input handle; action has no output handle", () => {
    expect(nodeMeta("trigger").hasInput).toBe(false);
    expect(nodeMeta("trigger").hasOutput).toBe(true);
    expect(nodeMeta("action").hasInput).toBe(true);
    expect(nodeMeta("action").hasOutput).toBe(false);
  });

  it("isNodeType rejects unknown kinds", () => {
    expect(isNodeType("trigger")).toBe(true);
    expect(isNodeType("bogus")).toBe(false);
  });

  it("defaultConfigFor returns a fresh object per call", () => {
    const a = defaultConfigFor("condition");
    a.value = 999;
    const b = defaultConfigFor("condition");
    expect(b.value).toBe(0);
  });
});

describe("toFlow", () => {
  it("maps backend nodes/edges to React Flow shape", () => {
    const { nodes, edges } = toFlow(
      [
        { id: "t", node_type: "trigger", config: { metric: "temp" }, position: { x: 10, y: 20 } },
        { id: "a", node_type: "action", config: { type: "notify", message: "hi" } },
      ],
      [{ id: "e1", from_node_id: "t", to_node_id: "a" }]
    );
    expect(nodes[0]).toMatchObject({
      id: "t",
      type: "rule",
      position: { x: 10, y: 20 },
      data: { nodeType: "trigger", config: { metric: "temp" } },
    });
    // Missing position falls back to a laid-out default.
    expect(nodes[1].position).toEqual({ x: 220, y: 80 });
    expect(edges[0]).toMatchObject({ id: "e1", source: "t", target: "a" });
  });
});

describe("validateFlow", () => {
  it("accepts a single-trigger linear chain", () => {
    const { nodes, edges } = toFlow(
      [
        { id: "t", node_type: "trigger", config: {} },
        { id: "c", node_type: "condition", config: {} },
        { id: "a", node_type: "action", config: {} },
      ],
      [
        { id: "e1", from_node_id: "t", to_node_id: "c" },
        { id: "e2", from_node_id: "c", to_node_id: "a" },
      ]
    );
    expect(validateFlow(nodes, edges)).toEqual([]);
  });

  it("flags zero or multiple triggers", () => {
    const two = toFlow(
      [
        { id: "t1", node_type: "trigger", config: {} },
        { id: "t2", node_type: "trigger", config: {} },
      ],
      []
    );
    expect(validateFlow(two.nodes, two.edges).join(" ")).toMatch(/only one trigger/i);

    const none = toFlow([{ id: "c", node_type: "condition", config: {} }], []);
    expect(validateFlow(none.nodes, none.edges).join(" ")).toMatch(/exactly one trigger/i);
  });

  it("flags edges that reference a missing node", () => {
    const nodes = [{ id: "t", type: "rule", position: { x: 0, y: 0 }, data: { nodeType: "trigger", config: {} } }];
    const edges = [{ id: "e", source: "t", target: "ghost" }];
    expect(validateFlow(nodes, edges).join(" ")).toMatch(/no longer exists/i);
  });
});

describe("makeNodeId", () => {
  it("returns an id not already in use", () => {
    expect(makeNodeId(["n1", "n2"])).toBe("n3");
    expect(makeNodeId([])).toBe("n1");
  });
});

describe("describeNode", () => {
  it("summarizes each node kind", () => {
    expect(describeNode("trigger", { metric: "temp" })).toBe("metric: temp");
    expect(describeNode("condition", { metric: "temp", op: ">", value: 40 })).toBe("temp > 40");
    expect(describeNode("delay", { seconds: 30 })).toBe("wait 30s");
    expect(describeNode("action", { type: "command", command: "pump", value: "on" })).toBe("command pump=on");
    expect(describeNode("action", { type: "notify", message: "hot" })).toBe("notify: hot");
  });
});

describe("round-trip property (backend -> React Flow -> backend)", () => {
  // Generators constrained to the valid input space: known node kinds, integer
  // positions, and edges that only reference generated node ids.
  const nodeArb = fc.record({
    id: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => /\S/.test(s)),
    node_type: fc.constantFrom(...NODE_TYPES),
    config: fc.dictionary(
      fc.string({ minLength: 1, maxLength: 6 }),
      fc.oneof(fc.integer(), fc.string({ maxLength: 10 }), fc.boolean())
    ),
    position: fc.record({
      x: fc.integer({ min: -1000, max: 1000 }),
      y: fc.integer({ min: -1000, max: 1000 }),
    }),
  });

  it("preserves node type, config, position, and edge wiring", () => {
    fc.assert(
      fc.property(
        fc
          .uniqueArray(nodeArb, {
            minLength: 1,
            maxLength: 8,
            selector: (n) => n.id,
          })
          .chain((nodes) => {
            const ids = nodes.map((n) => n.id);
            const edgeArb = fc.record({
              id: fc.uuid(),
              from_node_id: fc.constantFrom(...ids),
              to_node_id: fc.constantFrom(...ids),
            });
            return fc.tuple(
              fc.constant(nodes),
              fc.array(edgeArb, { maxLength: 12 })
            );
          }),
        ([nodes, edges]) => {
          const flow = toFlow(nodes, edges);
          const back = fromFlow(flow.nodes, flow.edges);

          // Node identity, kind, config, and (rounded) position survive.
          expect(back.nodes).toHaveLength(nodes.length);
          for (let i = 0; i < nodes.length; i += 1) {
            expect(back.nodes[i].id).toBe(String(nodes[i].id));
            expect(back.nodes[i].node_type).toBe(nodes[i].node_type);
            expect(back.nodes[i].config).toEqual(nodes[i].config);
            expect(back.nodes[i].position).toEqual(nodes[i].position);
          }

          // Edges map source/target -> from/to with the same references.
          expect(back.edges).toHaveLength(edges.length);
          for (let i = 0; i < edges.length; i += 1) {
            expect(back.edges[i].from).toBe(String(edges[i].from_node_id));
            expect(back.edges[i].to).toBe(String(edges[i].to_node_id));
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});
