import { useEffect, useMemo, useState } from "react";
import {
  Info,
  MagnifyingGlass,
  Plus,
  Trash,
  CaretUp,
  CaretDown,
  Rows,
  Funnel,
  Check,
  Tray,
} from "@phosphor-icons/react";
import { Dialog, DialogBody } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/apiClient";
import { listGroups } from "@/lib/devicesApi";
import DeviceTableWidget from "./widgets/DeviceTableWidget";

function deviceLabel(device) {
  return device.label || device.name || device.device_uid || "Device";
}

// Generate 10 dummy devices for live preview in Columns and Table Settings tabs
const DUMMY_PREVIEW_DEVICES = Array.from({ length: 10 }, (_, i) => ({
  id: `dummy-dev-${i + 1}`,
  name: "Device name",
  label: "Device name",
  device_uid: `DUMMY-UID-00${i + 1}`,
  status: i % 3 === 0 ? "online" : "offline",
  organization: "Main Organization",
  owner: "Device owner",
  temp: 20 + ((i * 3) % 15),
  humidity: 45 + ((i * 5) % 30),
  value: 40 + ((i * 7) % 35),
}));

export default function DeviceTableSettingsDialog({
  open,
  widget,
  devices = [],
  onClose,
  onSave,
}) {
  const [tab, setTab] = useState("data"); // "data" | "columns" | "tableSettings"
  const [draft, setDraft] = useState({});
  const [groups, setGroups] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterScope, setFilterScope] = useState("all"); // "all" | "mine" | "group"
  const [filterStatus, setFilterStatus] = useState("all"); // "all" | "online" | "offline"
  const [filterOpen, setFilterOpen] = useState(false);

  // Column creator state
  const [isAddingCol, setIsAddingCol] = useState(false);
  const [newColLabel, setNewColLabel] = useState("");
  const [newColMetric, setNewColMetric] = useState("");
  const [newColUnit, setNewColUnit] = useState("");
  const [availableDatastreams, setAvailableDatastreams] = useState([]);

  useEffect(() => {
    if (!widget) return;
    const config = widget.config || {};
    setTab("data");
    setDraft({
      title: config.title || "Device table",
      variant: "table",
      paletteId: "device_table",
      devicesPerPage: config.devicesPerPage ?? 10,
      defaultSortColumn: config.defaultSortColumn || "name",
      defaultSortDirection: config.defaultSortDirection || "asc",
      columns: Array.isArray(config.columns) ? [...config.columns] : [],
      selectedDeviceIds: config.selectedDeviceIds || "all", // "all" or string[]
    });
    setIsAddingCol(false);
    setSearchQuery("");
  }, [widget, open]);

  // Load groups for organization display
  useEffect(() => {
    if (!open) return undefined;
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
  }, [open]);

  // Discover datastreams from first few devices
  useEffect(() => {
    if (!open || devices.length === 0) return;
    const firstDev = devices[0];
    apiClient
      .get(`/devices/${firstDev.id}/datastreams`)
      .then((res) => {
        const list = res.data || [];
        setAvailableDatastreams(list);
      })
      .catch(() => {
        setAvailableDatastreams([]);
      });
  }, [open, devices]);

  if (!widget) return null;

  const setField = (key, value) => setDraft((curr) => ({ ...curr, [key]: value }));

  // Filter devices in Data tab
  const filteredDevices = useMemo(() => {
    let list = [...devices];

    if (filterStatus === "online") {
      list = list.filter((d) => d.status === "online");
    } else if (filterStatus === "offline") {
      list = list.filter((d) => d.status === "offline");
    }

    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter((d) => {
        const name = deviceLabel(d).toLowerCase();
        const uid = (d.device_uid || "").toLowerCase();
        const org = (groups.find((g) => g.id === d.group_id)?.name || "").toLowerCase();
        return name.includes(q) || uid.includes(q) || org.includes(q);
      });
    }

    return list;
  }, [devices, filterStatus, searchQuery, groups]);

  // Device selection handlers
  const isSelected = (id) => {
    if (draft.selectedDeviceIds === "all") return true;
    if (Array.isArray(draft.selectedDeviceIds)) {
      return draft.selectedDeviceIds.includes(String(id));
    }
    return false;
  };

  const toggleSelectDevice = (id) => {
    const strId = String(id);
    let next;
    if (draft.selectedDeviceIds === "all") {
      // Unchecking one from all
      next = devices.map((d) => String(d.id)).filter((i) => i !== strId);
    } else {
      const curr = Array.isArray(draft.selectedDeviceIds) ? draft.selectedDeviceIds : [];
      if (curr.includes(strId)) {
        next = curr.filter((i) => i !== strId);
      } else {
        next = [...curr, strId];
      }
    }
    setField("selectedDeviceIds", next);
  };

  const toggleSelectAll = () => {
    if (draft.selectedDeviceIds === "all" || (Array.isArray(draft.selectedDeviceIds) && draft.selectedDeviceIds.length === devices.length)) {
      setField("selectedDeviceIds", []);
    } else {
      setField("selectedDeviceIds", "all");
    }
  };

  const allSelected =
    draft.selectedDeviceIds === "all" ||
    (Array.isArray(draft.selectedDeviceIds) &&
      devices.length > 0 &&
      devices.every((d) => draft.selectedDeviceIds.includes(String(d.id))));

  // Add column
  const handleAddColumn = () => {
    const metric = newColMetric.trim();
    if (!metric) return;
    const label = newColLabel.trim() || metric;
    const newCol = {
      id: `col_${Date.now()}`,
      metric,
      label,
      unit: newColUnit.trim(),
    };
    setField("columns", [...(draft.columns || []), newCol]);
    setNewColLabel("");
    setNewColMetric("");
    setNewColUnit("");
    setIsAddingCol(false);
  };

  const handleRemoveColumn = (colId) => {
    setField(
      "columns",
      (draft.columns || []).filter((c) => c.id !== colId)
    );
  };

  const save = () => {
    onSave?.({
      ...draft,
      variant: "table",
      paletteId: "device_table",
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={draft.title || "Device table"}
      className="h-[680px] max-h-[min(680px,calc(100vh-2rem))] w-[1140px] max-w-[min(1140px,calc(100vw-2rem))]"
    >
      <DialogBody className="flex h-full flex-col px-0 pb-0 pt-0">
        {/* Navigation Tabs */}
        <div className="flex shrink-0 gap-8 border-b border-border px-6 pt-5 bg-background">
          {[
            { id: "data", label: "Data" },
            { id: "columns", label: "Columns" },
            { id: "tableSettings", label: "Table Settings" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              className={cn(
                "pb-3 text-sm font-semibold transition-all border-b-2 border-transparent",
                tab === t.id
                  ? "border-[#3dce4a] text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab 1: DATA */}
        {tab === "data" && (
          <div className="flex flex-1 flex-col min-h-0 overflow-y-auto px-6 py-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                  DEVICES
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Select devices that will be displayed in the table.
                </p>
              </div>

              {/* Search */}
              <div className="relative w-72">
                <MagnifyingGlass
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
                <input
                  type="text"
                  placeholder="Start typing"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#3dce4a]"
                />
              </div>
            </div>

            {/* Filter Pills Bar */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <div className="relative">
                <button
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded border border-dashed border-border px-3 py-1.5 text-xs font-medium hover:bg-muted/50",
                    filterStatus !== "all" && "border-[#3dce4a] text-[#3dce4a] bg-[#3dce4a]/5"
                  )}
                  onClick={() => setFilterOpen((o) => !o)}
                >
                  <Funnel size={12} />
                  <span>Add Filter</span>
                </button>
                {filterOpen && (
                  <div className="absolute left-0 top-full z-20 mt-1 w-44 rounded-md border border-border bg-popover p-1 shadow-lg text-xs">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left hover:bg-muted"
                      onClick={() => {
                        setFilterStatus("all");
                        setFilterOpen(false);
                      }}
                    >
                      <span>All statuses</span>
                      {filterStatus === "all" && <Check size={12} className="text-[#3dce4a]" />}
                    </button>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left hover:bg-muted"
                      onClick={() => {
                        setFilterStatus("online");
                        setFilterOpen(false);
                      }}
                    >
                      <span>Online only</span>
                      {filterStatus === "online" && <Check size={12} className="text-[#3dce4a]" />}
                    </button>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded px-2.5 py-1.5 text-left hover:bg-muted"
                      onClick={() => {
                        setFilterStatus("offline");
                        setFilterOpen(false);
                      }}
                    >
                      <span>Offline only</span>
                      {filterStatus === "offline" && <Check size={12} className="text-[#3dce4a]" />}
                    </button>
                  </div>
                )}
              </div>

              <button
                type="button"
                className={cn(
                  "inline-flex items-center gap-2 rounded px-3 py-1.5 text-xs font-semibold transition-colors",
                  filterScope === "all"
                    ? "bg-[#1f2429] text-white dark:bg-muted dark:text-foreground"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted"
                )}
                onClick={() => setFilterScope("all")}
              >
                <span>All</span>
                <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px] leading-tight">
                  {filteredDevices.length}
                </span>
              </button>

              <button
                type="button"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors",
                  filterScope === "mine"
                    ? "bg-[#1f2429] text-white dark:bg-muted dark:text-foreground"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted"
                )}
                onClick={() => setFilterScope("mine")}
              >
                <span>My devices</span>
              </button>

              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-muted"
                title="View mode"
              >
                <Rows size={14} />
              </button>
            </div>

            {/* Devices Selection Table */}
            <div className="mt-4 flex-1 overflow-auto rounded-md border border-border">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/30 text-muted-foreground select-none font-semibold">
                    <th className="w-10 px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleSelectAll}
                        className="h-3.5 w-3.5 rounded border-input accent-[#3dce4a]"
                        aria-label="Select all devices"
                      />
                    </th>
                    <th className="px-4 py-2.5">Device Name</th>
                    <th className="px-4 py-2.5">Organization</th>
                    <th className="px-4 py-2.5">Device owner</th>
                    <th className="px-4 py-2.5">Device Id</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filteredDevices.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-16 text-center text-muted-foreground">
                        <div className="flex flex-col items-center justify-center gap-2">
                          <Tray size={36} className="opacity-30" />
                          <p className="text-xs">No data</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    filteredDevices.map((dev) => {
                      const selected = isSelected(dev.id);
                      const isOnline = dev.status === "online";
                      const group = groups.find((g) => g.id === dev.group_id);

                      return (
                        <tr
                          key={dev.id}
                          className={cn(
                            "cursor-pointer hover:bg-muted/40 transition-colors",
                            selected && "bg-primary/[0.03]"
                          )}
                          onClick={() => toggleSelectDevice(dev.id)}
                        >
                          <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleSelectDevice(dev.id)}
                              className="h-3.5 w-3.5 rounded border-input accent-[#3dce4a]"
                            />
                          </td>
                          <td className="px-4 py-2.5 font-medium text-foreground">
                            <div className="flex items-center gap-2">
                              <span
                                className={cn(
                                  "h-2 w-2 rounded-full",
                                  isOnline ? "bg-[#22c55e]" : "bg-[#9ca3af]"
                                )}
                              />
                              <span>{deviceLabel(dev)}</span>
                            </div>
                          </td>
                          <td className="px-4 py-2.5 text-muted-foreground">
                            {group?.name || "Main Organization"}
                          </td>
                          <td className="px-4 py-2.5 text-muted-foreground">
                            {dev.owner_name || "Device owner"}
                          </td>
                          <td className="px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
                            {dev.device_uid || dev.id}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: COLUMNS */}
        {tab === "columns" && (
          <div className="flex flex-1 flex-col min-h-0 overflow-y-auto px-6 py-6">
            {/* Warning Banner */}
            <div className="flex items-center gap-2.5 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
              <Info size={16} className="shrink-0 text-amber-600 dark:text-amber-400" />
              <span>
                Preview displays dummy datastream values for 10 random devices. Real values will load
                after saving the dashboard.
              </span>
            </div>

            {/* Header + Add Column button */}
            <div className="mt-5 flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                  COLUMNS
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Add datastream columns and adjust them if needed
                </p>
              </div>

              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
                onClick={() => setIsAddingCol((v) => !v)}
              >
                <Plus size={13} weight="bold" />
                <span>Add Column</span>
              </button>
            </div>

            {/* Add Column Inline Popover / Form */}
            {isAddingCol && (
              <div className="mt-3 rounded-lg border border-border bg-card p-4 shadow-sm">
                <p className="text-xs font-bold uppercase tracking-wide text-foreground">
                  New Datastream Column
                </p>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground">
                      Column Title
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Temperature"
                      value={newColLabel}
                      onChange={(e) => setNewColLabel(e.target.value)}
                      className="mt-1 h-8 w-full rounded border border-input bg-background px-2.5 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground">
                      Datastream Metric
                    </label>
                    {availableDatastreams.length > 0 ? (
                      <select
                        value={newColMetric}
                        onChange={(e) => {
                          setNewColMetric(e.target.value);
                          if (!newColLabel) setNewColLabel(e.target.value);
                        }}
                        className="mt-1 h-8 w-full rounded border border-input bg-background px-2 text-xs"
                      >
                        <option value="">Select datastream...</option>
                        {availableDatastreams.map((ds) => (
                          <option key={ds.key} value={ds.key}>
                            {ds.key} {ds.unit ? `(${ds.unit})` : ""}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        placeholder="e.g. temp, value, humidity"
                        value={newColMetric}
                        onChange={(e) => setNewColMetric(e.target.value)}
                        className="mt-1 h-8 w-full rounded border border-input bg-background px-2.5 text-xs"
                      />
                    )}
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground">Unit</label>
                    <input
                      type="text"
                      placeholder="e.g. °C, %"
                      value={newColUnit}
                      onChange={(e) => setNewColUnit(e.target.value)}
                      className="mt-1 h-8 w-full rounded border border-input bg-background px-2.5 text-xs"
                    />
                  </div>
                </div>
                <div className="mt-3 flex justify-end gap-2">
                  <button
                    type="button"
                    className="rounded border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
                    onClick={() => setIsAddingCol(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="rounded bg-[#3dce4a] px-3 py-1 text-xs font-semibold text-black hover:brightness-95"
                    onClick={handleAddColumn}
                  >
                    Add
                  </button>
                </div>
              </div>
            )}

            {/* List of Configured Columns */}
            <div className="mt-3 flex flex-wrap gap-2">
              <div className="flex items-center gap-1.5 rounded border border-border bg-muted/30 px-3 py-1.5 text-xs font-medium text-foreground">
                <span>Device Name</span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  Default
                </span>
              </div>
              {(draft.columns || []).map((col) => (
                <div
                  key={col.id}
                  className="flex items-center gap-2 rounded border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm"
                >
                  <span>{col.label}</span>
                  <span className="text-[10px] text-muted-foreground">({col.metric})</span>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-red-500 transition-colors"
                    onClick={() => handleRemoveColumn(col.id)}
                    title="Remove column"
                  >
                    <Trash size={12} />
                  </button>
                </div>
              ))}
            </div>

            {/* Live Table Preview with Dummy Values */}
            <div className="mt-6 flex-1 overflow-hidden rounded-md border border-border">
              <DeviceTableWidget
                widget={{
                  config: {
                    ...draft,
                    devicesPerPage: 10,
                  },
                }}
                previewDevices={DUMMY_PREVIEW_DEVICES}
                previewDummyValues
                readOnly
              />
            </div>
          </div>
        )}

        {/* Tab 3: TABLE SETTINGS */}
        {tab === "tableSettings" && (
          <div className="grid min-h-0 flex-1 lg:grid-cols-2">
            {/* Left Column: Form Settings */}
            <div className="space-y-6 overflow-y-auto border-border px-6 py-6 lg:border-r">
              {/* Title */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-foreground">
                  TITLE
                </label>
                <input
                  type="text"
                  value={draft.title || ""}
                  onChange={(e) => setField("title", e.target.value)}
                  className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#3dce4a]"
                />
              </div>

              {/* Default Sort Order */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-foreground">
                  DEFAULT SORT ORDER
                </label>
                <div className="mt-2 flex items-center gap-2">
                  <select
                    value={draft.defaultSortColumn || "name"}
                    onChange={(e) => setField("defaultSortColumn", e.target.value)}
                    className="h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#3dce4a]"
                  >
                    <option value="name">Device Name</option>
                    {(draft.columns || []).map((col) => (
                      <option key={col.id} value={col.metric}>
                        {col.label || col.metric}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    className="flex h-10 w-10 items-center justify-center rounded-md border border-input bg-background hover:bg-muted"
                    title={draft.defaultSortDirection === "asc" ? "Ascending" : "Descending"}
                    onClick={() =>
                      setField(
                        "defaultSortDirection",
                        draft.defaultSortDirection === "asc" ? "desc" : "asc"
                      )
                    }
                  >
                    {draft.defaultSortDirection === "asc" ? (
                      <CaretUp size={16} weight="fill" className="text-[#3dce4a]" />
                    ) : (
                      <CaretDown size={16} weight="fill" className="text-[#3dce4a]" />
                    )}
                  </button>
                </div>
              </div>

              {/* Devices Per Page */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-foreground">
                  DEVICES PER PAGE
                </label>
                <div className="mt-2 inline-flex rounded-md bg-muted p-1">
                  {[10, 15, 20, 25, 30].map((num) => (
                    <button
                      key={num}
                      type="button"
                      className={cn(
                        "rounded px-3.5 py-1.5 text-xs font-semibold transition-all",
                        Number(draft.devicesPerPage) === num
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      onClick={() => setField("devicesPerPage", num)}
                    >
                      {num}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right Column: Live Widget Preview */}
            <div className="flex flex-col min-h-0 bg-muted/20 p-6 overflow-hidden">
              <div className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Preview
              </div>
              <div className="flex-1 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
                <DeviceTableWidget
                  widget={{
                    config: {
                      ...draft,
                    },
                  }}
                  previewDevices={DUMMY_PREVIEW_DEVICES}
                  previewDummyValues
                  readOnly
                />
              </div>
            </div>
          </div>
        )}

        {/* Modal Footer */}
        <div className="mt-auto flex shrink-0 items-center justify-end gap-2 border-t border-border bg-muted/30 px-6 py-4">
          <button
            type="button"
            className="h-9 rounded-md border border-border bg-background px-4 text-sm font-medium hover:bg-muted"
            onClick={onClose}
          >
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
