import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  Stack,
  MagnifyingGlass,
  ArrowClockwise,
  CircleNotch,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDevices,
  setFilters,
  selectDevices,
  selectDeviceGroups,
  selectDeviceFilters,
  selectDevicesStatus,
  selectDevicesError,
} from "@/store/devicesSlice";
import ProvisioningWizard from "@/components/devices/ProvisioningWizard";
import GroupManager from "@/components/devices/GroupManager";

// Device list view (Req 5.3-5.5): the fleet overview with status, group, and
// label columns, a search box, status/group filters, and entry points to the
// provisioning wizard and group manager. Rows link to the device detail view.
const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
];

export default function DeviceListPage() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const devices = useAppSelector(selectDevices);
  const groups = useAppSelector(selectDeviceGroups);
  const filters = useAppSelector(selectDeviceFilters);
  const status = useAppSelector(selectDevicesStatus);
  const error = useAppSelector(selectDevicesError);

  const [search, setSearch] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [groupsOpen, setGroupsOpen] = useState(false);

  // Fetch whenever server-side filters change.
  useEffect(() => {
    dispatch(
      fetchDevices({ groupId: filters.groupId, status: filters.status })
    );
  }, [dispatch, filters.groupId, filters.status]);

  const groupName = (id) => groups.find((g) => g.id === id)?.name;

  // Client-side label/uid search on top of the server-filtered list.
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter((d) => {
      const label = (d.label || "").toLowerCase();
      const uid = (d.device_uid || "").toLowerCase();
      return label.includes(q) || uid.includes(q);
    });
  }, [devices, search]);

  return (
    <section className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-primary">Devices</h1>
          <p className="text-sm text-muted-foreground">
            Provision and manage your device fleet.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setGroupsOpen(true)}>
            <Stack size={16} />
            Groups
          </Button>
          <Button onClick={() => setWizardOpen(true)}>
            <Plus size={16} />
            Provision device
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[12rem]">
          <MagnifyingGlass
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            className="pl-9"
            placeholder="Search by label or UID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label="Filter by status"
          value={filters.status || ""}
          onChange={(e) =>
            dispatch(setFilters({ status: e.target.value || null }))
          }
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by group"
          value={filters.groupId || ""}
          onChange={(e) =>
            dispatch(setFilters({ groupId: e.target.value || null }))
          }
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <option value="">All groups</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Refresh"
          onClick={() =>
            dispatch(
              fetchDevices({ groupId: filters.groupId, status: filters.status })
            )
          }
        >
          <ArrowClockwise size={16} />
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Device</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Group</th>
              <th className="px-4 py-3 font-medium">Maintenance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {status === "loading" ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-muted-foreground">
                  <CircleNotch size={20} className="mx-auto animate-spin" />
                </td>
              </tr>
            ) : status === "failed" ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-destructive">
                  {error || "Failed to load devices"}
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-muted-foreground">
                  {devices.length === 0
                    ? "No devices yet. Provision your first device."
                    : "No devices match your filters."}
                </td>
              </tr>
            ) : (
              visible.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => navigate(`/devices/${d.id}`)}
                  className="cursor-pointer transition-colors hover:bg-accent/50"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">
                      {d.label || d.device_uid || "(unnamed)"}
                    </div>
                    {d.label && d.device_uid ? (
                      <div className="text-xs text-muted-foreground">
                        {d.device_uid}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={d.status === "online" ? "success" : "muted"}>
                      {d.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {groupName(d.group_id) || "—"}
                  </td>
                  <td className="px-4 py-3">
                    {d.maintenance_mode ? (
                      <Badge variant="warning">Maintenance</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ProvisioningWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
      />
      <GroupManager open={groupsOpen} onClose={() => setGroupsOpen(false)} />
    </section>
  );
}
