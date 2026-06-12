import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Plus,
  PencilSimple,
  Check,
  CircleNotch,
  Plugs,
  PlugsConnected,
  Trash,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDashboards,
  fetchDashboard,
  createNewDashboard,
  saveLayout,
  addWidgetToDashboard,
  saveWidget,
  removeDashboard,
  removeWidget,
  setCurrentLayout,
  selectDashboards,
  selectCurrentDashboard,
  selectWidgets,
  selectDashboardsStatus,
  selectDashboardsError,
} from "@/store/dashboardsSlice";
import {
  fetchDevices,
  selectDevices,
} from "@/store/devicesSlice";
import DashboardCanvas from "@/components/dashboard/DashboardCanvas";
import AddWidgetMenu from "@/components/dashboard/AddWidgetMenu";
import WidgetSettingsDialog from "@/components/dashboard/WidgetSettingsDialog";
import { defaultConfigFor, defaultLayoutFor } from "@/lib/widgets";
import useDashboardTelemetry from "@/lib/useDashboardTelemetry";
import wsManager from "@/lib/websocket";
import { issueCommand } from "@/lib/commandsApi";
import { extractApiError } from "@/lib/authApi";

// Dashboard canvas page (Task 8.2, Req 7). Composes the dashboard selector,
// the React Grid Layout canvas, the 8 widget types, and the live WebSocket
// telemetry binding. Edit mode gates drag/drop/resize and widget management so
// viewing is interaction-safe.
export default function DashboardPage() {
  const dispatch = useAppDispatch();
  const dashboards = useAppSelector(selectDashboards);
  const current = useAppSelector(selectCurrentDashboard);
  const widgets = useAppSelector(selectWidgets);
  const status = useAppSelector(selectDashboardsStatus);
  const error = useAppSelector(selectDashboardsError);
  const devices = useAppSelector(selectDevices);

  const [selectedId, setSelectedId] = useState(null);
  const [editing, setEditing] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [configWidget, setConfigWidget] = useState(null);
  const [wsStatus, setWsStatus] = useState(wsManager.status);

  // Load the dashboard list and device list (for widget binding) once.
  useEffect(() => {
    dispatch(fetchDashboards());
    dispatch(fetchDevices({}));
  }, [dispatch]);

  // Auto-select the first dashboard once the list loads.
  useEffect(() => {
    if (!selectedId && dashboards.length > 0) {
      setSelectedId(dashboards[0].id);
    }
  }, [dashboards, selectedId]);

  // Load the selected dashboard's widgets + layout.
  useEffect(() => {
    if (selectedId) dispatch(fetchDashboard(selectedId));
  }, [dispatch, selectedId]);

  // Reflect WebSocket connection status in the header indicator.
  useEffect(() => wsManager.onStatus(setWsStatus), []);

  // Devices referenced by the current dashboard's widgets -> telemetry channels.
  const boundDeviceIds = useMemo(() => {
    const ids = new Set();
    for (const w of widgets) {
      const c = w.config || {};
      if (c.deviceId) ids.add(c.deviceId);
    }
    return [...ids];
  }, [widgets]);

  useDashboardTelemetry(boundDeviceIds);

  // --- Dashboard actions -------------------------------------------------
  const handleCreate = useCallback(async () => {
    const name = window.prompt("New dashboard name", "My dashboard");
    if (!name) return;
    const action = await dispatch(createNewDashboard({ name }));
    if (createNewDashboard.fulfilled.match(action)) {
      setSelectedId(action.payload.id);
      setEditing(true);
      toast.success("Dashboard created");
    } else {
      toast.error(action.payload?.message || "Failed to create dashboard");
    }
  }, [dispatch]);

  const handleDelete = useCallback(async () => {
    if (!current) return;
    const confirmed = window.confirm(
      `Delete dashboard "${current.name}"? This will remove all its widgets and cannot be undone.`
    );
    if (!confirmed) return;
    const action = await dispatch(removeDashboard(current.id));
    if (removeDashboard.fulfilled.match(action)) {
      setSelectedId(null);
      setEditing(false);
      toast.success("Dashboard deleted");
    } else {
      toast.error(action.payload?.message || "Failed to delete dashboard");
    }
  }, [dispatch, current]);

  // Persist reorder from drag-and-drop
  const handleReorder = useCallback(
    (layoutUpdates) => {
      if (!current || !editing) return;
      for (const item of layoutUpdates) {
        dispatch(
          saveWidget({
            dashboardId: current.id,
            widgetId: item.widgetId,
            changes: { layout: item.layout },
          })
        );
      }
    },
    [dispatch, current, editing]
  );

  const handleAddWidget = useCallback(
    async (type) => {
      if (!current) return;
      const config = defaultConfigFor(type);
      const layout = defaultLayoutFor(type, "new");
      delete layout.i;

      // Find the next available position: place at max bottom so horizontal
      // compaction fills the first available row slot automatically.
      let placeY = 0;
      if (widgets.length > 0) {
        for (const w of widgets) {
          const wl = w.layout || {};
          const bottom = (wl.y || 0) + (wl.h || 2);
          if (bottom > placeY) placeY = bottom;
        }
      }

      const action = await dispatch(
        addWidgetToDashboard({
          dashboardId: current.id,
          type,
          config,
          layout: { x: 0, y: placeY, w: layout.w, h: layout.h },
        })
      );
      if (addWidgetToDashboard.fulfilled.match(action)) {
        setConfigWidget(action.payload);
        toast.success("Widget added");
      } else {
        toast.error(action.payload?.message || "Failed to add widget");
      }
    },
    [dispatch, current, widgets]
  );

  const handleTogglePin = useCallback(
    (widget) => {
      if (!current) return;
      dispatch(
        saveWidget({
          dashboardId: current.id,
          widgetId: widget.id,
          changes: { pinned: !widget.pinned },
        })
      );
    },
    [dispatch, current]
  );

  const handleDeleteWidget = useCallback(
    async (widget) => {
      if (!current) return;
      const confirmed = window.confirm(`Delete this widget?`);
      if (!confirmed) return;
      const action = await dispatch(
        removeWidget({ dashboardId: current.id, widgetId: widget.id })
      );
      if (removeWidget.fulfilled.match(action)) {
        toast.success("Widget deleted");
      } else {
        toast.error(action.payload?.message || "Failed to delete widget");
      }
    },
    [dispatch, current]
  );

  const handleSaveConfig = useCallback(
    async (config) => {
      if (!current || !configWidget) return;
      const action = await dispatch(
        saveWidget({
          dashboardId: current.id,
          widgetId: configWidget.id,
          changes: { config },
        })
      );
      if (saveWidget.fulfilled.match(action)) {
        toast.success("Widget updated");
        setConfigWidget(null);
      } else {
        toast.error(action.payload?.message || "Failed to update widget");
      }
    },
    [dispatch, current, configWidget]
  );

  // Control-widget command emission. Sends the command to the backend which
  // publishes it to the device via MQTT (Req 9.1, 9.2).
  const handleCommand = useCallback(async (cmd) => {
    if (!cmd.deviceId) {
      toast.error("No device bound to this widget");
      return;
    }
    try {
      const result = await issueCommand(cmd.deviceId, {
        type: cmd.type,
        value: cmd.value,
        target: cmd.command || undefined,
      });
      if (result.status === "QUEUED") {
        toast.info("Command queued — device is offline, will execute on reconnect");
      } else {
        toast.success("Command sent to device");
      }
    } catch (err) {
      toast.error(extractApiError(err).message || "Failed to send command");
    }
  }, []);

  // --- Render ------------------------------------------------------------
  return (
    <section className="mx-auto max-w-7xl space-y-4 px-2">
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-card/80 px-4 py-3 shadow-sm backdrop-blur">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-foreground">📊 Dashboards</h1>
          {dashboards.length > 0 ? (
            <select
              aria-label="Select dashboard"
              value={selectedId || ""}
              onChange={(e) => {
                setSelectedId(e.target.value || null);
                setEditing(false);
              }}
              className="h-8 rounded-lg border border-input bg-background px-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {dashboards.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          ) : null}
          <span
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium"
            title={`Realtime: ${wsStatus}`}
          >
            {wsStatus === "open" ? (
              <PlugsConnected size={12} className="text-emerald-500" />
            ) : (
              <Plugs size={12} className="text-muted-foreground" />
            )}
            {wsStatus === "open" ? "Live" : wsStatus}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {current ? (
            <>
              {editing ? (
                <Button onClick={() => setAddOpen(true)} size="sm" variant="outline" className="rounded-lg">
                  <Plus size={14} />
                  Add widget
                </Button>
              ) : null}
              <Button
                size="sm"
                variant={editing ? "default" : "outline"}
                className="rounded-lg"
                onClick={() => setEditing((e) => !e)}
              >
                {editing ? <Check size={14} /> : <PencilSimple size={14} />}
                {editing ? "Done" : "Edit"}
              </Button>
              <Button variant="ghost" size="icon" onClick={handleDelete} title="Delete dashboard" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-destructive">
                <Trash size={14} />
              </Button>
            </>
          ) : null}
          <Button onClick={handleCreate} size="sm" className="rounded-lg">
            <Plus size={14} />
            New dashboard
          </Button>
        </div>
      </header>

      {status === "loading" && !current ? (
        <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
          <CircleNotch size={22} className="animate-spin" />
        </div>
      ) : status === "failed" && !current ? (
        <div className="flex min-h-[40vh] items-center justify-center text-destructive">
          {error || "Failed to load dashboards"}
        </div>
      ) : !current ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border text-muted-foreground">
          <p>No dashboards yet.</p>
          <Button onClick={handleCreate}>
            <Plus size={16} />
            Create your first dashboard
          </Button>
        </div>
      ) : (
        <DashboardCanvas
          widgets={widgets}
          editing={editing}
          onReorder={handleReorder}
          onCommand={handleCommand}
          onTogglePin={handleTogglePin}
          onConfigure={setConfigWidget}
          onDeleteWidget={handleDeleteWidget}
        />
      )}

      <AddWidgetMenu
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdd={handleAddWidget}
      />
      <WidgetSettingsDialog
        open={!!configWidget}
        widget={configWidget}
        devices={devices}
        onClose={() => setConfigWidget(null)}
        onSave={handleSaveConfig}
      />
    </section>
  );
}
