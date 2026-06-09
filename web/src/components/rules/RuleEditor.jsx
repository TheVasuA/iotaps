import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import RuleNode from "./RuleNode";
import NodeConfigDialog from "./NodeConfigDialog";
import {
  NODE_TYPES,
  nodeMeta,
  defaultConfigFor,
  makeNodeId,
  toFlow,
  fromFlow,
} from "@/lib/ruleGraph";

// Visual React Flow rule editor (Task 10.5, Req 10.1). Owns the canvas state
// (nodes/edges) for the rule currently being edited, a palette to add
// trigger/condition/action/delay nodes, per-node configuration, and edge
// drawing. The parent owns persistence: it seeds the editor via `nodes`/`edges`
// and reads the current graph back through `onChange` (already mapped to the
// backend shape by `fromFlow`).
const nodeTypes = { rule: RuleNode };

export default function RuleEditor({ nodes: initialNodes, edges: initialEdges, onChange, readOnly }) {
  const seeded = useMemo(
    () => toFlow(initialNodes || [], initialEdges || []),
    [initialNodes, initialEdges]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(seeded.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seeded.edges);
  const [configNodeId, setConfigNodeId] = useState(null);

  // Re-seed when the parent swaps in a different rule's graph.
  useEffect(() => {
    setNodes(seeded.nodes);
    setEdges(seeded.edges);
  }, [seeded, setNodes, setEdges]);

  // Push the mapped backend-shape graph up whenever the canvas changes.
  useEffect(() => {
    onChange?.(fromFlow(nodes, edges));
  }, [nodes, edges, onChange]);

  const onConfigure = useCallback((id) => setConfigNodeId(id), []);
  const onDeleteNode = useCallback(
    (id) => {
      setNodes((ns) => ns.filter((n) => n.id !== id));
      setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
    },
    [setNodes, setEdges]
  );

  // Inject per-node callbacks + read-only flag into node data for rendering.
  const renderedNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        data: { ...n.data, onConfigure, onDelete: onDeleteNode, readOnly },
      })),
    [nodes, onConfigure, onDeleteNode, readOnly]
  );

  const onConnect = useCallback(
    (connection) => {
      if (readOnly) return;
      setEdges((es) => addEdge(connection, es));
    },
    [setEdges, readOnly]
  );

  const addNode = useCallback(
    (type) => {
      setNodes((ns) => {
        const id = makeNodeId(ns.map((n) => n.id));
        // Stagger new nodes so they don't stack exactly on top of each other.
        const offset = ns.length * 40;
        const next = {
          id,
          type: "rule",
          position: { x: 80 + offset, y: 80 + (offset % 200) },
          data: { nodeType: type, config: defaultConfigFor(type) },
        };
        return [...ns, next];
      });
    },
    [setNodes]
  );

  const handleSaveConfig = useCallback(
    (id, config) => {
      setNodes((ns) =>
        ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, config } } : n))
      );
      setConfigNodeId(null);
    },
    [setNodes]
  );

  const configNode = useMemo(
    () => nodes.find((n) => n.id === configNodeId) || null,
    [nodes, configNodeId]
  );

  return (
    <div className="flex flex-col gap-3">
      {!readOnly ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Add node:</span>
          {NODE_TYPES.map((type) => (
            <Button
              key={type}
              size="sm"
              variant="outline"
              onClick={() => addNode(type)}
            >
              <Plus size={14} />
              {nodeMeta(type)?.label || type}
            </Button>
          ))}
        </div>
      ) : null}

      <div
        className="h-[60vh] w-full overflow-hidden rounded-lg border border-border bg-background"
        data-testid="rule-editor-canvas"
      >
        <ReactFlow
          nodes={renderedNodes}
          edges={edges}
          onNodesChange={readOnly ? undefined : onNodesChange}
          onEdgesChange={readOnly ? undefined : onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={!readOnly}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={16} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable className="!bg-muted" />
        </ReactFlow>
      </div>

      <NodeConfigDialog
        open={!!configNode}
        node={configNode}
        onClose={() => setConfigNodeId(null)}
        onSave={handleSaveConfig}
      />
    </div>
  );
}
