import { useEffect, useState, useMemo } from "react";
import { TreeView, CaretRight, CaretDown, Circle, Broadcast } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/devicesSlice";
import { selectLatest } from "@/store/dashboardsSlice";

// Build a tree structure from flat topic/message pairs
function buildTree(messages) {
  const root = { children: {}, messages: 0 };
  for (const msg of messages) {
    const parts = msg.topic.split("/");
    let node = root;
    for (const part of parts) {
      if (!node.children[part]) {
        node.children[part] = { children: {}, messages: 0, data: null, lastSeen: null };
      }
      node = node.children[part];
    }
    node.data = msg.data;
    node.lastSeen = msg.ts;
    node.messages += 1;
    root.messages += 1;
  }
  return root;
}

// Recursive tree node component
function TreeNode({ name, node, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const childKeys = Object.keys(node.children);
  const hasChildren = childKeys.length > 0;
  const isLeaf = !hasChildren && node.data != null;

  return (
    <div style={{ paddingLeft: depth > 0 ? 16 : 0 }}>
      <div
        className="group flex items-center gap-1.5 rounded px-2 py-1 hover:bg-accent/50 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        {hasChildren ? (
          expanded ? <CaretDown size={14} className="shrink-0 text-muted-foreground" /> : <CaretRight size={14} className="shrink-0 text-muted-foreground" />
        ) : (
          <Circle size={8} weight="fill" className="shrink-0 text-emerald-500 ml-[3px] mr-[3px]" />
        )}
        <span className="text-sm font-medium text-foreground">{name}</span>
        {node.messages > 0 && hasChildren && (
          <span className="text-[10px] text-muted-foreground ml-1">
            ({childKeys.length} topics, {node.messages} msg)
          </span>
        )}
        {isLeaf && node.data && (
          <code className="ml-2 truncate text-xs text-primary max-w-[400px]">
            = {typeof node.data === "string" ? node.data : JSON.stringify(node.data)}
          </code>
        )}
      </div>
      {expanded && hasChildren && (
        <div>
          {childKeys.sort().map((key) => (
            <TreeNode key={key} name={key} node={node.children[key]} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MqttExplorerPage() {
  const devices = useAppSelector(selectDevices);
  const [filter, setFilter] = useState("");

  // Build mock topic tree from devices + their latest telemetry
  const messages = useMemo(() => {
    const msgs = [];
    for (const d of devices) {
      const baseTopic = `iotaps/${d.org_id}/${d.id}`;
      // Add device status
      msgs.push({
        topic: `${baseTopic}/status`,
        data: d.status,
        ts: new Date().toISOString(),
      });
      // Add telemetry if we have the device ID in the label
      msgs.push({
        topic: `${baseTopic}/telemetry`,
        data: `{device: "${d.label || d.device_uid}"}`,
        ts: new Date().toISOString(),
      });
    }
    // Add system topics
    msgs.push({ topic: "$SYS/broker/clients/connected", data: String(devices.filter(d => d.status === "online").length), ts: new Date().toISOString() });
    msgs.push({ topic: "$SYS/broker/clients/total", data: String(devices.length), ts: new Date().toISOString() });
    msgs.push({ topic: "$SYS/broker/messages/received", data: "—", ts: null });
    msgs.push({ topic: "$SYS/broker/uptime", data: "running", ts: null });
    return msgs;
  }, [devices]);

  const filteredMessages = useMemo(() => {
    if (!filter.trim()) return messages;
    const q = filter.toLowerCase();
    return messages.filter((m) => m.topic.toLowerCase().includes(q));
  }, [messages, filter]);

  const tree = useMemo(() => buildTree(filteredMessages), [filteredMessages]);

  return (
    <section className="mx-auto max-w-5xl space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Broadcast size={22} className="text-primary" />
          <h1 className="text-xl font-bold">IoT Explorer</h1>
          <Badge variant="muted" className="text-[10px]">
            {messages.length} messages • {devices.length} devices
          </Badge>
        </div>
        <Input
          placeholder="Filter topics..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 w-48 text-sm"
        />
      </header>

      <div className="rounded-xl border border-border bg-card p-3 min-h-[60vh] overflow-auto font-mono text-sm">
        {Object.keys(tree.children).length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Broadcast size={32} className="mb-2" />
            <p>No MQTT messages yet</p>
            <p className="text-xs">Connect a device to see live topics here</p>
          </div>
        ) : (
          Object.keys(tree.children).sort().map((key) => (
            <TreeNode key={key} name={key} node={tree.children[key]} depth={0} />
          ))
        )}
      </div>
    </section>
  );
}
