import { useEffect, useMemo, useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

function deviceName(device) {
  return device.label || device.device_uid || device.name || "Device";
}

/** Picker for which devices a dashboard includes. */
export default function DashboardDataSourceDialog({
  open,
  devices = [],
  selectedIds,
  onClose,
  onSave,
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState(() => new Set());
  const [all, setAll] = useState(true);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const useAll = !Array.isArray(selectedIds);
    setAll(useAll);
    setPicked(new Set(useAll ? devices.map((d) => d.id) : selectedIds));
  }, [open, selectedIds, devices]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter((d) => deviceName(d).toLowerCase().includes(q));
  }, [devices, query]);

  const selectedDevices = devices.filter((d) => picked.has(d.id));

  const toggleAll = () => {
    if (all) {
      setAll(false);
      setPicked(new Set());
      return;
    }
    setAll(true);
    setPicked(new Set(devices.map((d) => d.id)));
  };

  const toggleOne = (id) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      setAll(next.size === devices.length && devices.length > 0);
      return next;
    });
  };

  const apply = () => {
    if (all || (devices.length > 0 && picked.size === devices.length)) {
      onSave?.(null);
      return;
    }
    onSave?.([...picked]);
  };

  return (
    <Dialog open={open} onClose={onClose} className="h-[min(680px,86vh)] max-w-5xl overflow-hidden">
      <div className="flex h-full min-h-0 flex-col">
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="flex min-h-0 flex-col px-6 pb-4 pt-6">
            <h2 className="pr-8 font-brand text-xl font-semibold text-foreground">
              Which devices do you want to include?
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Widgets on this dashboard only use devices from this selection.
            </p>

            <button
              type="button"
              className={cn("dash-source-all", all && "dash-source-all-on")}
              onClick={toggleAll}
            >
              All
              <span>{all ? devices.length : picked.size}</span>
            </button>

            <label className="dash-source-search">
              <MagnifyingGlass size={16} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search"
                aria-label="Search devices"
              />
            </label>

            <ul className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
              {filtered.map((device) => {
                const on = picked.has(device.id);
                return (
                  <li key={device.id}>
                    <button
                      type="button"
                      className={cn("dash-source-device", on && "dash-source-device-on")}
                      onClick={() => toggleOne(device.id)}
                    >
                      <span className="truncate">{deviceName(device)}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {device.status || "device"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <aside className="flex min-h-[12rem] items-center justify-center border-t border-border bg-muted/20 px-6 text-center md:border-l md:border-t-0">
            {selectedDevices.length === 0 ? (
              <p className="max-w-[14rem] text-sm text-muted-foreground">
                No devices match your current selection criteria
              </p>
            ) : (
              <ul className="max-h-full w-full space-y-2 overflow-y-auto text-left">
                {selectedDevices.map((device) => (
                  <li key={device.id} className="rounded-lg border border-border bg-card px-3 py-2">
                    <p className="truncate text-sm font-semibold text-foreground">{deviceName(device)}</p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {device.device_uid || device.id}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>

        <div className="flex items-center justify-between border-t border-border px-6 py-4">
          <button type="button" className="dash-builder-cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="dash-builder-apply" onClick={apply}>
            Next
          </button>
        </div>
      </div>
    </Dialog>
  );
}
