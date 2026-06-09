import { useEffect, useState } from "react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { widgetMeta } from "@/lib/widgets";

// Per-type settings form for a widget. Edits the widget `config` (device + metric
// binding, thresholds, ranges, command name) and saves it back via `onSave`.
// Keeps the field set minimal per widget type to avoid over-configuration.

const fieldsByType = {
  line: ["deviceId", "metric", "title", "maxPoints"],
  bar: ["deviceId", "metric", "title", "maxPoints"],
  gauge: ["deviceId", "metric", "title", "min", "max", "unit", "zones"],
  value: ["deviceId", "metric", "title", "unit", "precision"],
  map: ["deviceId", "latMetric", "lonMetric", "title"],
  toggle: ["deviceId", "metric", "title", "command"],
  slider: ["deviceId", "metric", "title", "command", "min", "max", "step"],
  alert_badge: ["deviceId", "metric", "title", "operator", "threshold"],
};

const NUMERIC = new Set([
  "min",
  "max",
  "step",
  "threshold",
  "precision",
  "maxPoints",
]);

const LABELS = {
  deviceId: "Device",
  metric: "Metric",
  latMetric: "Latitude metric",
  lonMetric: "Longitude metric",
  title: "Title",
  unit: "Unit",
  command: "Command name",
  min: "Min",
  max: "Max",
  step: "Step",
  threshold: "Threshold",
  precision: "Decimals",
  operator: "Operator",
  maxPoints: "Max points",
};

export default function WidgetSettingsDialog({
  open,
  widget,
  devices = [],
  onClose,
  onSave,
}) {
  const [config, setConfig] = useState({});

  useEffect(() => {
    if (widget) setConfig({ ...(widget.config || {}) });
  }, [widget]);

  if (!widget) return null;

  const meta = widgetMeta(widget.type);
  const fields = fieldsByType[widget.type] || ["deviceId", "metric", "title"];

  const setField = (key, value) => setConfig((c) => ({ ...c, [key]: value }));

  const handleSave = () => {
    // Coerce numeric fields so the stored config has correct types.
    const next = { ...config };
    for (const key of Object.keys(next)) {
      if (NUMERIC.has(key) && next[key] !== "" && next[key] != null) {
        const n = Number(next[key]);
        if (Number.isFinite(n)) next[key] = n;
      }
    }
    onSave?.(next);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`${meta?.label || widget.type} settings`}
      description="Bind this widget to a device metric and adjust its options."
    >
      <DialogBody className="space-y-3">
        {fields.map((key) => {
          if (key === "deviceId") {
            return (
              <div key={key} className="space-y-1">
                <Label htmlFor={`f-${key}`}>{LABELS[key]}</Label>
                <select
                  id={`f-${key}`}
                  value={config.deviceId || ""}
                  onChange={(e) => setField("deviceId", e.target.value || "")}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <option value="">Select a device…</option>
                  {devices.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label || d.device_uid || d.id}
                    </option>
                  ))}
                </select>
              </div>
            );
          }
          if (key === "operator") {
            return (
              <div key={key} className="space-y-1">
                <Label htmlFor={`f-${key}`}>{LABELS[key]}</Label>
                <select
                  id={`f-${key}`}
                  value={config.operator || ">"}
                  onChange={(e) => setField("operator", e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  {[">", ">=", "<", "<=", "==", "!="].map((op) => (
                    <option key={op} value={op}>
                      {op}
                    </option>
                  ))}
                </select>
              </div>
            );
          }
          if (key === "zones") {
            const zones = Array.isArray(config.zones) ? config.zones : [
              { value: 40, color: "#22c55e" },
              { value: 70, color: "#eab308" },
              { value: 100, color: "#ef4444" },
            ];
            return (
              <div key={key} className="space-y-2">
                <Label>Color Zones</Label>
                {zones.map((z, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground w-6">≤</span>
                    <Input
                      type="number"
                      value={z.value}
                      onChange={(e) => {
                        const updated = [...zones];
                        updated[i] = { ...updated[i], value: Number(e.target.value) };
                        setField("zones", updated);
                      }}
                      className="w-20 h-8 text-sm"
                      placeholder="Value"
                    />
                    <input
                      type="color"
                      value={z.color}
                      onChange={(e) => {
                        const updated = [...zones];
                        updated[i] = { ...updated[i], color: e.target.value };
                        setField("zones", updated);
                      }}
                      className="h-8 w-8 cursor-pointer rounded border border-input p-0.5"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const updated = zones.filter((_, idx) => idx !== i);
                        setField("zones", updated);
                      }}
                      className="text-xs text-destructive hover:underline"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setField("zones", [...zones, { value: 100, color: "#3b82f6" }])}
                  className="text-xs text-primary hover:underline"
                >
                  + Add zone
                </button>
                <p className="text-[10px] text-muted-foreground">
                  Gauge color changes when value reaches each threshold
                </p>
              </div>
            );
          }
          return (
            <div key={key} className="space-y-1">
              <Label htmlFor={`f-${key}`}>{LABELS[key] || key}</Label>
              <Input
                id={`f-${key}`}
                type={NUMERIC.has(key) ? "number" : "text"}
                value={config[key] ?? ""}
                onChange={(e) => setField(key, e.target.value)}
              />
            </div>
          );
        })}
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
