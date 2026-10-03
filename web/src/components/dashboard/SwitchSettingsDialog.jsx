import { useEffect, useState } from "react";
import { Info } from "@phosphor-icons/react";
import { Dialog, DialogBody } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import WidgetPalettePreview from "./WidgetPalettePreview";

const DEFAULT_COLOR = "#3dce4a";

function deviceLabel(device) {
  return device.label || device.name || device.device_uid || "Device";
}

/** Blynk-style Switch settings. The datastream field selects a device. */
export default function SwitchSettingsDialog({ open, widget, devices = [], onClose, onSave }) {
  const [tab, setTab] = useState("data");
  const [draft, setDraft] = useState({});

  useEffect(() => {
    if (!widget) return;
    const config = widget.config || {};
    setTab("data");
    setDraft({
      ...config,
      title: config.title || "Switch",
      hideTitle: Boolean(config.hideTitle),
      color: config.color || DEFAULT_COLOR,
      showLabels: config.showLabels !== false,
      onLabel: config.onLabel ?? "On",
      offLabel: config.offLabel ?? "Off",
      labelPosition: config.labelPosition || "right",
    });
  }, [widget]);

  useEffect(() => {
    if (!open || !draft.deviceId) return undefined;
    let cancelled = false;
    apiClient
      .get(`/devices/${draft.deviceId}/datastreams`)
      .then(({ data }) => {
        if (cancelled) return;
        const list = data || [];
        const pick =
          list.find((item) => item.pin_type === "toggle") ||
          list.find((item) => item.key) ||
          null;
        if (!pick) return;
        setDraft((current) =>
          current.deviceId === draft.deviceId && !current.metric
            ? { ...current, metric: pick.key }
            : current
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, draft.deviceId]);

  if (!widget) return null;

  const setField = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const previewLabel = draft.showLabels ? draft.offLabel || "Off" : undefined;

  const save = () => {
    onSave?.({
      ...draft,
      title: draft.title || "Switch",
      variant: draft.variant || "switch",
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Switch"
      className="h-[680px] max-h-[min(680px,calc(100vh-2rem))] w-[1100px] max-w-[min(1100px,calc(100vw-2rem))]"
    >
      <DialogBody className="flex h-full flex-col px-0 pb-0 pt-0">
        <div className="flex shrink-0 gap-6 border-b border-border px-6 pt-5">
          {["data", "design"].map((id) => (
            <button
              key={id}
              type="button"
              className={cn("ws-tab", tab === id && "ws-tab-on")}
              onClick={() => setTab(id)}
            >
              {id === "data" ? "Data" : "Design"}
            </button>
          ))}
        </div>

        {tab === "data" ? (
          <div className="grid min-h-0 flex-1 gap-8 px-6 py-6 lg:grid-cols-2">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-foreground">Datastream</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Min/Max values of datastreams will be used as On/Off values.
              </p>
              <select
                className="mt-3 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={draft.deviceId || ""}
                onChange={(event) => {
                  const deviceId = event.target.value;
                  setDraft((current) => ({
                    ...current,
                    deviceId,
                    metric: deviceId === current.deviceId ? current.metric : "",
                  }));
                }}
                aria-label="Device"
              >
                <option value="">Select...</option>
                {devices.map((device) => (
                  <option key={device.id} value={device.id}>
                    {deviceLabel(device)}
                  </option>
                ))}
              </select>
            </div>
            <div className="h-fit rounded-lg bg-muted/70 p-4 text-sm text-foreground/80">
              <p className="flex items-center gap-2 font-semibold text-foreground">
                <Info size={16} />
                Warning
              </p>
              <p className="mt-2 leading-relaxed">
                Ensure that the datastreams are of <strong>Integer</strong> or <strong>Double</strong> type
                across all selected templates. Datastreams of other types will be ignored.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 lg:grid-cols-2">
            <div className="space-y-5 border-border px-6 py-6 lg:border-r">
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wide">Title</span>
                <input
                  className="mt-2 h-10 w-full rounded-md border border-input px-3 text-sm"
                  value={draft.title || ""}
                  onChange={(event) => setField("title", event.target.value)}
                />
              </label>
              <label className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(draft.hideTitle)}
                  onChange={(event) => setField("hideTitle", event.target.checked)}
                />
                Hide widget title
              </label>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">Color</p>
                <label className="mt-2 inline-flex h-8 w-8 cursor-pointer overflow-hidden rounded-sm border border-border">
                  <input
                    type="color"
                    className="h-10 w-10 cursor-pointer border-0 p-0"
                    value={draft.color || DEFAULT_COLOR}
                    onChange={(event) => setField("color", event.target.value)}
                    aria-label="Switch color"
                  />
                </label>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">On/Off labels</p>
                <label className="mt-2 flex items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[#3dce4a]"
                    checked={draft.showLabels !== false}
                    onChange={(event) => setField("showLabels", event.target.checked)}
                  />
                  Show on/off labels
                </label>
                {draft.showLabels !== false ? (
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <label className="block text-xs text-muted-foreground">
                      On label
                      <input
                        className="mt-1 h-10 w-full rounded-md border border-input px-3 text-sm text-foreground"
                        value={draft.onLabel || ""}
                        onChange={(event) => setField("onLabel", event.target.value)}
                      />
                    </label>
                    <label className="block text-xs text-muted-foreground">
                      Off label
                      <input
                        className="mt-1 h-10 w-full rounded-md border border-input px-3 text-sm text-foreground"
                        value={draft.offLabel || ""}
                        onChange={(event) => setField("offLabel", event.target.value)}
                      />
                    </label>
                  </div>
                ) : null}
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Label position</p>
                <div className="mt-2 inline-flex rounded-md bg-muted p-0.5">
                  {["left", "right"].map((position) => (
                    <button
                      key={position}
                      type="button"
                      className={cn(
                        "rounded px-3 py-1.5 text-sm capitalize",
                        draft.labelPosition === position ? "bg-background font-semibold shadow-sm" : "text-muted-foreground"
                      )}
                      onClick={() => setField("labelPosition", position)}
                    >
                      {position}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-center bg-muted/40 p-6">
              <div className="wb-card w-44">
                {draft.hideTitle ? null : <span className="wb-card-title">{draft.title || "Switch"}</span>}
                <WidgetPalettePreview
                  kind="switch"
                  on={false}
                  color={draft.color}
                  stateLabel={previewLabel}
                  labelPosition={draft.labelPosition || "right"}
                />
              </div>
            </div>
          </div>
        )}

        <div className="mt-auto flex shrink-0 items-center justify-end gap-2 border-t border-border bg-muted/30 px-6 py-4">
          <button type="button" className="h-9 rounded-md border border-border bg-background px-4 text-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="ws-save" onClick={save}>
            Save
          </button>
        </div>
      </DialogBody>
    </Dialog>
  );
}
