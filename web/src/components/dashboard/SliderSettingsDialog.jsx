import { useEffect, useState } from "react";
import { Info } from "@phosphor-icons/react";
import { Dialog, DialogBody } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import WidgetPalettePreview from "./WidgetPalettePreview";

const DEFAULT_COLOR = "#2ec9a0";

function deviceLabel(device) {
  return device.label || device.name || device.device_uid || "Device";
}

/** Blynk-style Slider settings. The datastream field selects a device. */
export default function SliderSettingsDialog({ open, widget, devices = [], onClose, onSave }) {
  const [tab, setTab] = useState("data");
  const [draft, setDraft] = useState({});

  useEffect(() => {
    if (!widget) return;
    const config = widget.config || {};
    setTab("data");
    setDraft({
      ...config,
      title: config.title || "Slider",
      color: config.color || DEFAULT_COLOR,
      showFineControls: Boolean(config.showFineControls),
      step: config.step ?? 1,
      valuePosition: config.valuePosition || "left",
      orientation: config.orientation || "horizontal",
      min: config.min ?? 0,
      max: config.max ?? 255,
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
          list.find((item) => item.pin_type === "slider") ||
          list.find((item) => item.pin_type === "sensor") ||
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

  const save = () => {
    const step = Number(draft.step);
    onSave?.({
      ...draft,
      title: draft.title || "Slider",
      variant: draft.variant || "slider",
      step: Number.isFinite(step) ? step : 1,
      showFineControls: Boolean(draft.showFineControls),
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Slider"
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
            <div className="space-y-5 overflow-y-auto border-border px-6 py-6 lg:border-r">
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wide">Title</span>
                <input
                  className="mt-2 h-10 w-full rounded-md border border-input px-3 text-sm"
                  value={draft.title || ""}
                  onChange={(event) => setField("title", event.target.value)}
                />
              </label>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">Color</p>
                <label className="mt-2 inline-flex h-8 w-8 cursor-pointer overflow-hidden rounded-sm border border-border">
                  <input
                    type="color"
                    className="h-10 w-10 cursor-pointer border-0 p-0"
                    value={draft.color || DEFAULT_COLOR}
                    onChange={(event) => setField("color", event.target.value)}
                    aria-label="Slider color"
                  />
                </label>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">Fine controls</p>
                <label className="mt-2 flex items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[#3dce4a]"
                    checked={Boolean(draft.showFineControls)}
                    onChange={(event) => setField("showFineControls", event.target.checked)}
                  />
                  Show fine controls
                </label>
                {draft.showFineControls ? (
                  <label className="mt-3 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                    Fine control step
                    <input
                      type="number"
                      min="0"
                      className="mt-1 h-10 w-full rounded-md border border-input px-3 text-sm font-normal normal-case text-foreground"
                      value={draft.step ?? 1}
                      onChange={(event) => setField("step", event.target.value)}
                    />
                  </label>
                ) : null}
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Value position</p>
                <div className="mt-2 inline-flex rounded-md bg-muted p-0.5">
                  {["left", "right"].map((position) => (
                    <button
                      key={position}
                      type="button"
                      className={cn(
                        "rounded px-3 py-1.5 text-sm capitalize",
                        (draft.valuePosition || "left") === position
                          ? "bg-background font-semibold shadow-sm"
                          : "text-muted-foreground"
                      )}
                      onClick={() => setField("valuePosition", position)}
                    >
                      {position}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Orientation</p>
                <div className="mt-2 inline-flex rounded-md bg-muted p-0.5">
                  {["horizontal", "vertical"].map((orientation) => (
                    <button
                      key={orientation}
                      type="button"
                      className={cn(
                        "rounded px-3 py-1.5 text-sm capitalize",
                        (draft.orientation || "horizontal") === orientation
                          ? "bg-background font-semibold shadow-sm"
                          : "text-muted-foreground"
                      )}
                      onClick={() => setField("orientation", orientation)}
                    >
                      {orientation}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-center bg-muted/40 p-6">
              <div className={cn("wb-card", draft.orientation === "vertical" ? "w-28 h-56" : "w-52")}>
                <span className="wb-card-title">{draft.title || "Slider"}</span>
                <WidgetPalettePreview
                  kind="slider"
                  value={0}
                  color={draft.color || DEFAULT_COLOR}
                  showFineControls={Boolean(draft.showFineControls)}
                  valuePosition={draft.valuePosition || "left"}
                  fineStep={draft.step || 1}
                  sliderMin={draft.min}
                  sliderMax={draft.max}
                  orientation={draft.orientation || "horizontal"}
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
