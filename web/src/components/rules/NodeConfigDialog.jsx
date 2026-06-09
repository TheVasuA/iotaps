import { useEffect, useState } from "react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { nodeMeta } from "@/lib/ruleGraph";

// Per-node configuration editor for the visual rule editor (Task 10.5).
// Renders the right fields for the node's kind:
//   trigger   -> metric
//   condition -> metric (optional), operator, value
//   delay     -> seconds
//   action    -> type (notify|command|webhook) + type-specific fields
// Edits are local until Save so the canvas only updates on confirm.

const OPERATORS = [">", ">=", "<", "<=", "==", "!="];
const ACTION_TYPES = ["notify", "command", "webhook"];

export default function NodeConfigDialog({ open, node, onClose, onSave }) {
  const [config, setConfig] = useState({});

  useEffect(() => {
    if (node) setConfig({ ...(node.data?.config || {}) });
  }, [node]);

  if (!node) return null;

  const nodeType = node.data?.nodeType;
  const meta = nodeMeta(nodeType);
  const set = (key, value) => setConfig((c) => ({ ...c, [key]: value }));

  const handleSave = () => {
    onSave?.(node.id, config);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Configure ${meta?.label || "node"}`}
      description={meta?.description}
    >
      <DialogBody className="space-y-4">
        {nodeType === "trigger" ? (
          <Field label="Metric" htmlFor="cfg-metric">
            <Input
              id="cfg-metric"
              value={config.metric ?? ""}
              placeholder="e.g. temp"
              onChange={(e) => set("metric", e.target.value)}
            />
          </Field>
        ) : null}

        {nodeType === "condition" ? (
          <>
            <Field label="Metric (optional)" htmlFor="cfg-metric">
              <Input
                id="cfg-metric"
                value={config.metric ?? ""}
                placeholder="defaults to trigger metric"
                onChange={(e) => set("metric", e.target.value)}
              />
            </Field>
            <Field label="Operator" htmlFor="cfg-op">
              <select
                id="cfg-op"
                value={config.op ?? ">"}
                onChange={(e) => set("op", e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Value" htmlFor="cfg-value">
              <Input
                id="cfg-value"
                type="number"
                value={config.value ?? 0}
                onChange={(e) => set("value", toNumber(e.target.value))}
              />
            </Field>
          </>
        ) : null}

        {nodeType === "delay" ? (
          <Field label="Delay (seconds)" htmlFor="cfg-seconds">
            <Input
              id="cfg-seconds"
              type="number"
              min={0}
              value={config.seconds ?? 0}
              onChange={(e) => set("seconds", toNumber(e.target.value))}
            />
          </Field>
        ) : null}

        {nodeType === "action" ? (
          <>
            <Field label="Action type" htmlFor="cfg-type">
              <select
                id="cfg-type"
                value={config.type ?? "notify"}
                onChange={(e) => set("type", e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                {ACTION_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>

            {(config.type ?? "notify") === "notify" ? (
              <Field label="Message" htmlFor="cfg-message">
                <Input
                  id="cfg-message"
                  value={config.message ?? ""}
                  placeholder="Notification text"
                  onChange={(e) => set("message", e.target.value)}
                />
              </Field>
            ) : null}

            {config.type === "command" ? (
              <>
                <Field label="Command" htmlFor="cfg-command">
                  <Input
                    id="cfg-command"
                    value={config.command ?? ""}
                    placeholder="e.g. pump"
                    onChange={(e) => set("command", e.target.value)}
                  />
                </Field>
                <Field label="Value" htmlFor="cfg-cmd-value">
                  <Input
                    id="cfg-cmd-value"
                    value={config.value ?? ""}
                    placeholder="e.g. on"
                    onChange={(e) => set("value", e.target.value)}
                  />
                </Field>
              </>
            ) : null}

            {config.type === "webhook" ? (
              <Field label="Webhook URL" htmlFor="cfg-url">
                <Input
                  id="cfg-url"
                  value={config.url ?? ""}
                  placeholder="https://..."
                  onChange={(e) => set("url", e.target.value)}
                />
              </Field>
            ) : null}
          </>
        ) : null}
      </DialogBody>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={handleSave}>Save</Button>
      </DialogFooter>
    </Dialog>
  );
}

function Field({ label, htmlFor, children }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function toNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
