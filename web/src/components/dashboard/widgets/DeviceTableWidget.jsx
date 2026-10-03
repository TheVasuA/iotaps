import { useMemo, useState } from "react";
import {
  CaretUp,
  CaretDown,
  CaretLeft,
  CaretRight,
  Tray,
  MagnifyingGlass,
  Cpu,
} from "@phosphor-icons/react";
import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/devicesSlice";
import { selectLatest } from "@/store/dashboardsSlice";
import { readMetric, formatValue } from "@/lib/widgets";
import { cn } from "@/lib/utils";

function DeviceRowMetric({ deviceId, metric, unit }) {
  const latest = useAppSelector(selectLatest(deviceId));
  const val = readMetric(latest?.data, metric);
  if (val == null) return <span className="text-slate-400 font-mono text-xs">—</span>;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100/90 border border-slate-200/60 text-slate-800 tabular-nums">
      {typeof val === "number" ? formatValue(val, 1) : String(val)}
      {unit ? <span className="text-[10px] text-slate-500 font-sans font-bold">{unit}</span> : null}
    </span>
  );
}

export default function DeviceTableWidget({
  widget,
  previewDevices,
  previewDummyValues = false,
  readOnly = false,
}) {
  const config = widget?.config || {};
  const storeDevices = useAppSelector(selectDevices);
  const devices = previewDevices || storeDevices || [];

  const title = config.title || "Device table";
  const devicesPerPage = Number(config.devicesPerPage) || 10;
  const configuredColumns = config.columns || [];
  const selectedScope = config.selectedDeviceIds || "all";
  const defaultSortCol = config.defaultSortColumn || "name";
  const defaultSortDir = config.defaultSortDirection || "asc";

  const [sortCol, setSortCol] = useState(defaultSortCol);
  const [sortDir, setSortDir] = useState(defaultSortDir);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all"); // "all" | "online" | "offline"

  // Filter devices based on selection scope, search, and status
  const filteredDevices = useMemo(() => {
    if (!Array.isArray(devices)) return [];
    let list = devices;

    // Scope filter
    if (selectedScope !== "all" && Array.isArray(selectedScope) && selectedScope.length > 0) {
      const idSet = new Set(selectedScope.map(String));
      list = list.filter((d) => idSet.has(String(d.id)));
    }

    // Status filter
    if (statusFilter === "online") {
      list = list.filter((d) => d.status === "online");
    } else if (statusFilter === "offline") {
      list = list.filter((d) => d.status !== "online");
    }

    // Search query
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((d) => {
        const name = (d.label || d.name || "").toLowerCase();
        const uid = (d.device_uid || d.id || "").toLowerCase();
        return name.includes(q) || uid.includes(q);
      });
    }

    return list;
  }, [devices, selectedScope, statusFilter, search]);

  // Sort devices
  const sortedDevices = useMemo(() => {
    const list = [...filteredDevices];
    list.sort((a, b) => {
      let valA = "";
      let valB = "";
      if (sortCol === "name") {
        valA = (a.label || a.name || a.device_uid || "").toLowerCase();
        valB = (b.label || b.name || b.device_uid || "").toLowerCase();
      } else if (sortCol === "status") {
        valA = a.status || "";
        valB = b.status || "";
      } else if (sortCol === "id") {
        valA = a.device_uid || a.id || "";
        valB = b.device_uid || b.id || "";
      } else {
        valA = a[sortCol] != null ? a[sortCol] : "";
        valB = b[sortCol] != null ? b[sortCol] : "";
      }

      if (valA < valB) return sortDir === "asc" ? -1 : 1;
      if (valA > valB) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return list;
  }, [filteredDevices, sortCol, sortDir]);

  // Counts for filters
  const onlineCount = useMemo(() => {
    return Array.isArray(devices) ? devices.filter((d) => d.status === "online").length : 0;
  }, [devices]);
  const offlineCount = (devices?.length || 0) - onlineCount;

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sortedDevices.length / devicesPerPage));
  const safePage = Math.min(page, totalPages);
  const startIndex = (safePage - 1) * devicesPerPage;
  const pageDevices = sortedDevices.slice(startIndex, startIndex + devicesPerPage);

  const toggleSort = (colId) => {
    if (sortCol === colId) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(colId);
      setSortDir("asc");
    }
  };

  const pageNumbers = useMemo(() => {
    const pages = [];
    const maxVisible = 5;
    let start = Math.max(1, safePage - Math.floor(maxVisible / 2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }, [safePage, totalPages]);

  return (
    <div
      className="flex h-full w-full flex-col overflow-hidden bg-white text-slate-800 rounded-lg select-none"
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* Minimal Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/50 px-3 py-1.5 text-xs">
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-100/80 p-0.5">
          <button
            type="button"
            className={cn(
              "px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors cursor-pointer",
              statusFilter === "all"
                ? "bg-white text-slate-900 shadow-2xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            )}
            onClick={() => {
              setStatusFilter("all");
              setPage(1);
            }}
          >
            All ({devices.length})
          </button>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors cursor-pointer",
              statusFilter === "online"
                ? "bg-white text-slate-900 shadow-2xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            )}
            onClick={() => {
              setStatusFilter("online");
              setPage(1);
            }}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Online ({onlineCount})
          </button>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors cursor-pointer",
              statusFilter === "offline"
                ? "bg-white text-slate-900 shadow-2xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            )}
            onClick={() => {
              setStatusFilter("offline");
              setPage(1);
            }}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
            Offline ({offlineCount})
          </button>
        </div>

        {/* Quick Search Input */}
        <div className="relative min-w-[130px] max-w-[180px]">
          <MagnifyingGlass size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="h-6 w-full rounded-md border border-slate-200/70 bg-white pl-6 pr-2 text-[11px] text-slate-800 placeholder-slate-400 focus:border-slate-400 focus:outline-none"
          />
        </div>
      </div>

      {/* Table Data Container */}
      <div className="flex-1 overflow-x-auto overflow-y-auto min-h-0">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50/95 backdrop-blur-md text-[11px] font-bold tracking-wider text-slate-500 uppercase select-none">
              <th
                className="cursor-pointer px-4 py-2.5 hover:text-slate-900 transition-colors"
                onClick={() => toggleSort("name")}
              >
                <div className="flex items-center gap-1.5">
                  <span>Device Name</span>
                  {sortCol === "name" ? (
                    sortDir === "asc" ? (
                      <CaretUp size={12} weight="fill" className="text-primary" />
                    ) : (
                      <CaretDown size={12} weight="fill" className="text-primary" />
                    )
                  ) : (
                    <CaretUp size={12} weight="regular" className="opacity-25" />
                  )}
                </div>
              </th>

              <th
                className="cursor-pointer px-3 py-2.5 hover:text-slate-900 transition-colors"
                onClick={() => toggleSort("status")}
              >
                <div className="flex items-center gap-1.5">
                  <span>Status</span>
                  {sortCol === "status" ? (
                    sortDir === "asc" ? (
                      <CaretUp size={12} weight="fill" className="text-primary" />
                    ) : (
                      <CaretDown size={12} weight="fill" className="text-primary" />
                    )
                  ) : (
                    <CaretUp size={12} weight="regular" className="opacity-25" />
                  )}
                </div>
              </th>

              {configuredColumns.map((col) => (
                <th
                  key={col.id || col.metric}
                  className="cursor-pointer px-4 py-2.5 hover:text-slate-900 transition-colors whitespace-nowrap"
                  onClick={() => toggleSort(col.metric || col.id)}
                >
                  <div className="flex items-center gap-1.5">
                    <span>{col.label || col.metric}</span>
                    {sortCol === (col.metric || col.id) ? (
                      sortDir === "asc" ? (
                        <CaretUp size={12} weight="fill" className="text-primary" />
                      ) : (
                        <CaretDown size={12} weight="fill" className="text-primary" />
                      )
                    ) : (
                      <CaretUp size={12} weight="regular" className="opacity-25" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pageDevices.length === 0 ? (
              <tr>
                <td
                  colSpan={2 + configuredColumns.length}
                  className="py-12 text-center text-slate-400"
                >
                  <div className="flex flex-col items-center justify-center gap-2">
                    <Tray size={32} className="opacity-40" />
                    <p className="text-xs font-medium">No matching devices found</p>
                  </div>
                </td>
              </tr>
            ) : (
              pageDevices.map((dev, idx) => {
                const isOnline = dev.status === "online";
                const devName = dev.label || dev.name || dev.device_uid || "Device";
                const devUid = dev.device_uid || String(dev.id).slice(0, 8);

                return (
                  <tr
                    key={dev.id || `dev-${idx}`}
                    className="hover:bg-slate-50/70 transition-colors group"
                  >
                    <td className="px-4 py-2 font-medium text-slate-900">
                      <div className="flex items-center gap-2">
                        <Cpu size={14} className="text-slate-400 group-hover:text-slate-700 transition-colors shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold text-xs text-slate-800 truncate max-w-[180px]" title={devName}>
                            {devName}
                          </p>
                          <p className="font-mono text-[9px] text-slate-400 truncate">
                            {devUid}
                          </p>
                        </div>
                      </div>
                    </td>

                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                        <span
                          className={cn(
                            "h-1.5 w-1.5 rounded-full",
                            isOnline ? "bg-emerald-500" : "bg-slate-300"
                          )}
                        />
                        {isOnline ? "Online" : "Offline"}
                      </span>
                    </td>

                    {configuredColumns.map((col, cIdx) => (
                      <td
                        key={col.id || col.metric || cIdx}
                        className="px-4 py-2.5 text-xs text-slate-800 whitespace-nowrap"
                      >
                        {previewDummyValues ? (
                          <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100/90 border border-slate-200/60 text-slate-800 tabular-nums">
                            {dev[col.metric] ?? dev[col.id] ?? (40 + ((idx * 7 + cIdx * 11) % 45))}
                            {col.unit ? <span className="text-[10px] text-slate-500 font-sans font-bold">{col.unit}</span> : ""}
                          </span>
                        ) : (
                          <DeviceRowMetric
                            deviceId={dev.id}
                            metric={col.metric}
                            unit={col.unit}
                          />
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {sortedDevices.length > 0 && (
        <div className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50/70 py-2 px-3 text-xs select-none">
          <span className="text-[11px] text-slate-500">
            Showing <strong className="font-semibold text-slate-700">{startIndex + 1}–{Math.min(startIndex + devicesPerPage, sortedDevices.length)}</strong> of <strong className="font-semibold text-slate-700">{sortedDevices.length}</strong>
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-2xs hover:bg-slate-100 transition-colors",
                safePage <= 1 && "pointer-events-none opacity-40"
              )}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              aria-label="Previous page"
            >
              <CaretLeft size={13} weight="bold" />
            </button>

            {pageNumbers.map((pNum) => {
              const isActive = pNum === safePage;
              return (
                <button
                  key={pNum}
                  type="button"
                  className={cn(
                    "flex h-7 min-w-[28px] items-center justify-center rounded-lg px-2 text-xs font-bold transition-all",
                    isActive
                      ? "bg-primary text-white shadow-xs border border-primary"
                      : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-100"
                  )}
                  onClick={() => setPage(pNum)}
                >
                  {pNum}
                </button>
              );
            })}

            <button
              type="button"
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-2xs hover:bg-slate-100 transition-colors",
                safePage >= totalPages && "pointer-events-none opacity-40"
              )}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              aria-label="Next page"
            >
              <CaretRight size={13} weight="bold" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
