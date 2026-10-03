import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogBody } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { listGroups } from "@/lib/devicesApi";
import WidgetPalettePreview from "./WidgetPalettePreview";

const TITLES = {
  label: "Label",
  count: "Device Count",
  online: "Devices online now",
};

function deviceLabel(device) {
  return device.label || device.name || device.device_uid || "Device";
}

/** Settings for Label, Device count, and Devices online now. */
export default function TileSettingsDialog({ open, widget, devices = [], onClose, onSave }) {
  const kind = widget?.config?.variant === "online" || widget?.config?.paletteId === "devices_online"
    ? "online"
    : widget?.config?.variant === "count" || widget?.config?.paletteId === "device_count"
      ? "count"
      : "label";
  const [tab, setTab] = useState("data");
  const [draft, setDraft] = useState({});
  const [groups, setGroups] = useState([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!widget) return;
    const config = widget.config || {};
    setTab("data");
    setDraft({
      ...config,
      title: config.title || TITLES[kind],
      align: config.align || "left",
      showLevel: Boolean(config.showLevel),
      levelMin: config.levelMin ?? 0,
      levelMax: config.levelMax ?? 100,
      levelColor: config.levelColor || "#2f6fed",
      levelPosition: config.levelPosition || (kind === "label" ? "vertical" : "horizontal"),
      colorByValue: Boolean(config.colorByValue),
      gradientFrom: config.gradientFrom || "#ffffff",
      gradientTo: config.gradientTo || "#d9f5df",
      background: config.background || "#ffffff",
      deviceScope: config.deviceScope || "all",
    });
  }, [widget, kind]);

  useEffect(() => {
    if (!open || kind === "label") return undefined;
    let cancelled = false;
    listGroups()
      .then((rows) => {
        if (!cancelled) setGroups(rows || []);
      })
      .catch(() => {
        if (!cancelled) setGroups([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, kind]);

  useEffect(() => {
    if (!open || kind !== "label" || !draft.deviceId) return undefined;
    let cancelled = false;
    apiClient
      .get(`/devices/${draft.deviceId}/datastreams`)
      .then(({ data }) => {
        if (cancelled) return;
        const pick = (data || []).find((item) => item.key);
        if (!pick) return;
        setDraft((current) =>
          current.deviceId === draft.deviceId && !current.metric ? { ...current, metric: pick.key } : current
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, kind, draft.deviceId]);

  const matched = useMemo(() => {
    const source =
      draft.deviceScope === "group" && draft.groupId
        ? devices.filter((device) => String(device.group_id) === String(draft.groupId))
        : devices;
    const list = kind === "online" ? source.filter((device) => device.status === "online") : source;
    const text = query.trim().toLowerCase();
    return text ? list.filter((device) => deviceLabel(device).toLowerCase().includes(text)) : list;
  }, [devices, draft.deviceScope, draft.groupId, kind, query]);

  if (!widget) return null;

  const setField = (key, value) => setDraft((current) => ({ ...current, [key]: value }));
  const previewValue = kind === "label" ? 75 : matched.length;

  const save = () => {
    onSave?.({
      ...draft,
      title: draft.title || TITLES[kind],
      variant: kind === "count" ? "count" : kind === "online" ? "online" : "label",
      levelMin: Number(draft.levelMin) || 0,
      levelMax: Number(draft.levelMax) || 100,
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={TITLES[kind]}
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
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            {kind === "label" ? (
              <div className="max-w-md">
                <p className="text-xs font-bold uppercase tracking-wide">Datastream</p>
                <p className="mt-1 text-xs text-muted-foreground">Choose the device whose value this label shows.</p>
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
            ) : (
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">Devices</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {kind === "online"
                    ? "Count only devices that are online now."
                    : "Choose which devices to count."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={cn("ws-scope", draft.deviceScope !== "group" && "ws-scope-on")}
                    onClick={() => setField("deviceScope", "all")}
                  >
                    All devices
                  </button>
                  <button
                    type="button"
                    className={cn("ws-scope", draft.deviceScope === "group" && "ws-scope-on")}
                    onClick={() => setField("deviceScope", "group")}
                  >
                    Device group
                  </button>
                </div>
                {draft.deviceScope === "group" ? (
                  <select
                    className="mt-3 h-10 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm"
                    value={draft.groupId || ""}
                    onChange={(event) => setField("groupId", event.target.value)}
                    aria-label="Device group"
                  >
                    <option value="">Select a group...</option>
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                ) : null}
                <input
                  className="mt-4 h-10 w-full max-w-md rounded-md border border-input px-3 text-sm"
                  placeholder="Start typing"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search devices"
                />
                <p className="mt-4 text-sm text-muted-foreground">
                  {matched.length} {kind === "online" ? "online" : "devices"}
                </p>
                {matched.length === 0 ? (
                  <p className="mt-10 text-center text-sm text-muted-foreground">No data</p>
                ) : (
                  <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-sm">
                    {matched.map((device) => (
                      <li key={device.id} className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted">
                        <span>{deviceLabel(device)}</span>
                        <span className="text-xs text-muted-foreground">{device.status}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
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
                <p className="text-xs font-bold uppercase tracking-wide">
                  {kind === "label" ? "Content alignment" : "Value alignment"}
                </p>
                <div className="mt-2 inline-flex rounded-md bg-muted p-0.5">
                  {["left", "center", "right"].map((align) => (
                    <button
                      key={align}
                      type="button"
                      className={cn(
                        "rounded px-3 py-1.5 text-sm capitalize",
                        (draft.align || "left") === align ? "bg-background font-semibold shadow-sm" : "text-muted-foreground"
                      )}
                      onClick={() => setField("align", align)}
                    >
                      {align}
                    </button>
                  ))}
                </div>
              </div>
              {kind === "label" ? (
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide">Widget background</p>
                  <label className="mt-2 flex items-center gap-3 text-sm">
                    <input
                      type="checkbox"
                      className="accent-[#3dce4a]"
                      checked={Boolean(draft.colorByValue)}
                      onChange={(event) => setField("colorByValue", event.target.checked)}
                    />
                    Change color based on value
                  </label>
                  {draft.colorByValue ? (
                    <div className="mt-3 flex gap-3">
                      <label className="text-xs text-muted-foreground">
                        From
                        <input
                          type="color"
                          className="mt-1 block h-8 w-10"
                          value={draft.gradientFrom || "#ffffff"}
                          onChange={(event) => setField("gradientFrom", event.target.value)}
                        />
                      </label>
                      <label className="text-xs text-muted-foreground">
                        To
                        <input
                          type="color"
                          className="mt-1 block h-8 w-10"
                          value={draft.gradientTo || "#d9f5df"}
                          onChange={(event) => setField("gradientTo", event.target.value)}
                        />
                      </label>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide">Widget background</p>
                  <input
                    type="color"
                    className="mt-2 h-8 w-10"
                    value={draft.background || "#ffffff"}
                    onChange={(event) => setField("background", event.target.value)}
                    aria-label="Widget background"
                  />
                </div>
              )}
              <div>
                <p className="text-xs font-bold uppercase tracking-wide">Level</p>
                <label className="mt-2 flex items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[#3dce4a]"
                    checked={Boolean(draft.showLevel)}
                    onChange={(event) => setField("showLevel", event.target.checked)}
                  />
                  Show level
                </label>
                {draft.showLevel ? (
                  <div className="mt-3 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                        Min
                        <input
                          type="number"
                          className="mt-1 h-10 w-full rounded-md border border-input px-3 text-sm font-normal normal-case text-foreground"
                          value={draft.levelMin ?? 0}
                          onChange={(event) => setField("levelMin", event.target.value)}
                        />
                      </label>
                      <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                        Max
                        <input
                          type="number"
                          className="mt-1 h-10 w-full rounded-md border border-input px-3 text-sm font-normal normal-case text-foreground"
                          value={draft.levelMax ?? 100}
                          onChange={(event) => setField("levelMax", event.target.value)}
                        />
                      </label>
                    </div>
                    {kind === "label" ? (
                      <div>
                        <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Level position</p>
                        <div className="mt-2 inline-flex rounded-md bg-muted p-0.5">
                          {["vertical", "horizontal"].map((position) => (
                            <button
                              key={position}
                              type="button"
                              className={cn(
                                "rounded px-3 py-1.5 text-sm capitalize",
                                draft.levelPosition === position
                                  ? "bg-background font-semibold shadow-sm"
                                  : "text-muted-foreground"
                              )}
                              onClick={() => setField("levelPosition", position)}
                            >
                              {position}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Level color</p>
                      <input
                        type="color"
                        className="mt-2 h-8 w-10"
                        value={draft.levelColor || "#2f6fed"}
                        onChange={(event) => setField("levelColor", event.target.value)}
                        aria-label="Level color"
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex items-center justify-center bg-muted/40 p-6">
              <div className="wb-card w-52" style={{ background: kind === "label" && draft.colorByValue ? draft.gradientTo : draft.background }}>
                <span className="wb-card-title">{draft.title || TITLES[kind]}</span>
                <WidgetPalettePreview
                  kind={kind === "count" ? "count" : kind === "online" ? "online" : "label"}
                  figure={String(previewValue)}
                  tileAlign={draft.align || "left"}
                  showLevel={Boolean(draft.showLevel)}
                  levelColor={draft.levelColor || "#2f6fed"}
                  levelPosition={draft.levelPosition || (kind === "label" ? "vertical" : "horizontal")}
                  levelPct={Math.min(100, Math.max(8, (Number(previewValue) / (Number(draft.levelMax) || 100)) * 100))}
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
