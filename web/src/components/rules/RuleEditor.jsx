import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
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
import { cn } from "@/lib/utils";

const nodeTypes = { rule: RuleNode };
const DND_TYPE = "application/iotaps-rule-node";

const PALETTE_SWATCH = {
  trigger: "bg-emerald-500",
  condition: "bg-amber-500",
  delay: "bg-sky-500",
  action: "bg-fuchsia-500",
};

function RuleEditorInner({
  nodes: initialNodes,
  edges: initialEdges,
  onChange,
  readOnly,
  onLog,
}) {
  const { screenToFlowPosition } = useReactFlow();
  const seeded = useMemo(
    () => toFlow(initialNodes || [], initialEdges || []),
    [initialNodes, initialEdges]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(seeded.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seeded.edges);
  const [configNodeId, setConfigNodeId] = useState(null);

  const log = useCallback(
    (message, level = "info") => {
      onLog?.({ ts: Date.now(), level, message });
    },
    [onLog]
  );

  useEffect(() => {
    setNodes(seeded.nodes);
    setEdges(seeded.edges);
  }, [seeded, setNodes, setEdges]);

  useEffect(() => {
    onChange?.(fromFlow(nodes, edges));
  }, [nodes, edges, onChange]);

  const onConfigure = useCallback((id) => setConfigNodeId(id), []);
  const onDeleteNode = useCallback(
    (id) => {
      setNodes((ns) => ns.filter((n) => n.id !== id));
      setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
      log(`Removed node ${id}`, "warn");
    },
    [setNodes, setEdges, log]
  );

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
      setEdges((es) => addEdge({ ...connection, type: "smoothstep" }, es));
      log(`Wire ${connection.source} → ${connection.target}`, "success");
    },
    [setEdges, readOnly, log]
  );

  const addNodeAt = useCallback(
    (type, position) => {
      setNodes((ns) => {
        const id = makeNodeId(ns.map((n) => n.id));
        const next = {
          id,
          type: "rule",
          position: position || { x: 80, y: 80 },
          data: { nodeType: type, config: defaultConfigFor(type) },
        };
        return [...ns, next];
      });
      log(`Added ${nodeMeta(type)?.label || type} node`, "info");
    },
    [setNodes, log]
  );

  const addNode = useCallback((type) => addNodeAt(type), [addNodeAt]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      if (readOnly) return;
      const type = event.dataTransfer.getData(DND_TYPE);
      if (!type || !NODE_TYPES.includes(type)) return;
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      addNodeAt(type, position);
    },
    [readOnly, screenToFlowPosition, addNodeAt]
  );

  const handleSaveConfig = useCallback(
    (id, config) => {
      setNodes((ns) =>
        ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, config } } : n))
      );
      setConfigNodeId(null);
      log(`Updated config on ${id}`, "info");
    },
    [setNodes, log]
  );

  const configNode = useMemo(
    () => nodes.find((n) => n.id === configNodeId) || null,
    [nodes, configNodeId]
  );

  return (
    <div className="nodered-editor flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {!readOnly ? (
          <aside
            className="nodered-palette shrink-0 border-b md:w-52 md:border-b-0 md:border-r"
            aria-label="Node palette"
          >
            <div className="border-b border-inherit px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Logic nodes
              </p>
              <p className="text-xs text-muted-foreground">Drag onto the canvas or click to add</p>
            </div>
            <ul className="flex gap-1 overflow-x-auto p-2 md:flex-col md:overflow-x-visible">
              {NODE_TYPES.map((type) => {
                const meta = nodeMeta(type);
                return (
                  <li key={type} className="min-w-[140px] md:min-w-0">
                    <button
                      type="button"
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData(DND_TYPE, type);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onClick={() => addNode(type)}
                      className="flex w-full cursor-grab items-start gap-2 rounded-md border border-transparent px-2 py-2 text-left transition-colors hover:border-border hover:bg-background/80 active:cursor-grabbing"
                    >
                      <span
                        className={cn(
                          "mt-0.5 h-3 w-3 shrink-0 rounded-sm",
                          PALETTE_SWATCH[type] || "bg-muted-foreground"
                        )}
                        aria-hidden
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-foreground">
                          {meta?.label || type}
                        </span>
                        <span className="line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                          {meta?.description}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
        ) : null}

        <div
          className="nodered-workspace relative min-h-[40vh] min-w-0 flex-1 md:min-h-0"
          data-testid="rule-editor-canvas"
        >
          <ReactFlow
            nodes={renderedNodes}
            edges={edges}
            onNodesChange={readOnly ? undefined : onNodesChange}
            onEdgesChange={readOnly ? undefined : onEdgesChange}
            onConnect={onConnect}
            onDragOver={onDragOver}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            nodesDraggable={!readOnly}
            nodesConnectable={!readOnly}
            elementsSelectable={!readOnly}
            defaultEdgeOptions={{ type: "smoothstep", animated: false }}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} size={1} color="hsl(var(--flow-grid))" />
            <Controls showInteractive={false} className="!border-border !bg-card" />
            <MiniMap
              pannable
              zoomable
              className="!border !border-border"
              nodeColor={(n) => {
                const t = n.data?.nodeType;
                if (t === "trigger") return "#10b981";
                if (t === "condition") return "#f59e0b";
                if (t === "delay") return "#0ea5e9";
                if (t === "action") return "#d946ef";
                return "#64748b";
              }}
            />
          </ReactFlow>
        </div>
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

export default function RuleEditor(props) {
  return (
    <ReactFlowProvider>
      <RuleEditorInner {...props} />
    </ReactFlowProvider>
  );
}
