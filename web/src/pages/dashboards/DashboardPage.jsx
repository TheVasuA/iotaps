import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CircleNotch } from "@phosphor-icons/react";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDashboards,
  fetchDashboard,
  createNewDashboard,
  addWidgetToDashboard,
  saveWidget,
  removeDashboard,
  removeWidget,
  copyDashboard,
  markDashboardHomepage,
  saveDashboardSettings,
  saveDashboardName,
  selectDashboards,
  selectCurrentDashboard,
  selectWidgets,
  selectDashboardsStatus,
  selectDashboardsError,
  selectDashboardSaving,
  selectHomepageId,
} from "@/store/dashboardsSlice";
import { fetchDevices, selectDevices } from "@/store/devicesSlice";
import { selectUser } from "@/store/authSlice";
import DashboardCanvas, { GRID_COLS } from "@/components/dashboard/DashboardCanvas";
import DashboardEmptyState from "@/components/dashboard/DashboardEmptyState";
import DashboardListSidebar from "@/components/dashboard/DashboardListSidebar";
import DashboardBuilderToolbox from "@/components/dashboard/DashboardBuilderToolbox";
import DashboardBuilderHeader from "@/components/dashboard/DashboardBuilderHeader";
import DashboardBuilderFilters from "@/components/dashboard/DashboardBuilderFilters";
import DashboardDataSourceDialog from "@/components/dashboard/DashboardDataSourceDialog";
import DashboardAccessDrawer from "@/components/dashboard/DashboardAccessDrawer";
import DashboardViewToolbar from "@/components/dashboard/DashboardViewToolbar";
import WidgetSettingsDialog from "@/components/dashboard/WidgetSettingsDialog";
import { defaultConfigFor, defaultLayoutFor } from "@/lib/widgets";
import { paletteItem } from "@/lib/widgetPalette";
import useDashboardTelemetry from "@/lib/useDashboardTelemetry";
import { issueCommand } from "@/lib/commandsApi";
import { extractApiError } from "@/lib/authApi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";

const MAX_DASHBOARDS = 10;

function nextDashboardName(dashboards) {
  let name = "New dashboard";
  let n = 2;
  const taken = new Set(dashboards.map((d) => d.name.toLowerCase()));
  while (taken.has(name.toLowerCase())) {
    name = `New dashboard ${n++}`;
  }
  return name;
}

export default function DashboardPage() {
  const dispatch = useAppDispatch();
  const dashboards = useAppSelector(selectDashboards);
  const current = useAppSelector(selectCurrentDashboard);
  const widgets = useAppSelector(selectWidgets);
  const status = useAppSelector(selectDashboardsStatus);
  const error = useAppSelector(selectDashboardsError);
  const saving = useAppSelector(selectDashboardSaving);
  const devices = useAppSelector(selectDevices);
  const user = useAppSelector(selectUser);
  const homepageId = useAppSelector(selectHomepageId);
  const location = useLocation();
  const navigate = useNavigate();
  const isHomeRoute = location.pathname === "/homepage";

  const [selectedId, setSelectedId] = useState(null);
  const [editing, setEditing] = useState(false);
  const [editDraftName, setEditDraftName] = useState("");
  const [editSessionNew, setEditSessionNew] = useState(false);
  const canvasHostRef = useRef(null);
  const [configWidget, setConfigWidget] = useState(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    dispatch(fetchDashboards());
    dispatch(fetchDevices({}));
  }, [dispatch]);

  const openedHome = useRef(false);
  useEffect(() => {
    if (!user?.id || dashboards.length === 0) return;
    if (isHomeRoute) {
      if (homepageId) setSelectedId(homepageId);
      return;
    }
    if (openedHome.current) return;
    openedHome.current = true;
    const focus = location.state?.dashboardId;
    const focused = focus && dashboards.some((item) => item.id === focus) ? focus : null;
    setSelectedId(focused || homepageId || dashboards[0].id);
  }, [dashboards, user?.id, isHomeRoute, homepageId, location.state?.dashboardId]);

  useEffect(() => {
    if (selectedId) dispatch(fetchDashboard(selectedId));
  }, [dispatch, selectedId]);

  useEffect(() => {
    if (editing && current) {
      setEditDraftName(current.name || "");
    }
  }, [editing, current?.id, current?.name]);

  const settings = current?.settings || {};
  const timeRange = settings.time_range || "1w";
  const selectedDeviceIds = Array.isArray(settings.device_ids) ? settings.device_ids : null;
  const sourceLabel =
    selectedDeviceIds == null
      ? "All devices in this workspace"
      : selectedDeviceIds.length === 1
        ? "1 device"
        : `${selectedDeviceIds.length} devices`;

  const boundDeviceIds = useMemo(() => {
    const ids = new Set();
    for (const w of widgets) {
      const c = w.config || {};
      if (c.deviceId) ids.add(c.deviceId);
    }
    return [...ids];
  }, [widgets]);

  useDashboardTelemetry(boundDeviceIds);

  const persistSettings = useCallback(
    (patch) => {
      if (!current) return;
      dispatch(
        saveDashboardSettings({
          id: current.id,
          settings: { ...settings, ...patch },
        })
      );
    },
    [dispatch, current, settings]
  );

  const startNewDashboard = useCallback(async () => {
    if (dashboards.length >= MAX_DASHBOARDS) {
      toast.error("Dashboard limit reached — upgrade for more");
      return;
    }
    const name = nextDashboardName(dashboards);
    const action = await dispatch(createNewDashboard({ name }));
    if (createNewDashboard.fulfilled.match(action)) {
      setSelectedId(action.payload.id);
      setEditDraftName(action.payload.name);
      setEditSessionNew(true);
      setEditing(true);
    } else {
      toast.error(action.payload?.message || "Failed to create dashboard");
    }
  }, [dispatch, dashboards]);

  const handleCreate = useCallback(() => {
    startNewDashboard();
  }, [startNewDashboard]);

  const handleSaveEdit = useCallback(async () => {
    if (!current) return;
    const name = editDraftName.trim();
    if (!name) {
      toast.error("Dashboard name is required");
      return;
    }
    if (dashboards.some((d) => d.id !== current.id && d.name.toLowerCase() === name.toLowerCase())) {
      toast.error("A dashboard with this name already exists");
      return;
    }
    if (name !== current.name) {
      const action = await dispatch(saveDashboardName({ id: current.id, name }));
      if (!saveDashboardName.fulfilled.match(action)) {
        toast.error(action.payload?.message || "Failed to save name");
        return;
      }
    }
    setEditSessionNew(false);
    setEditing(false);
    toast.success("Dashboard saved");
  }, [dispatch, current, editDraftName, dashboards]);

  const handleCancelEdit = useCallback(async () => {
    if (!current) {
      setEditing(false);
      return;
    }
    if (editSessionNew && widgets.length === 0) {
      const id = current.id;
      const action = await dispatch(removeDashboard(id));
      if (removeDashboard.fulfilled.match(action)) {
        setSelectedId(null);
        setEditing(false);
        setEditSessionNew(false);
      }
      return;
    }
    setEditDraftName(current.name);
    setEditSessionNew(false);
    setEditing(false);
  }, [dispatch, current, editSessionNew, widgets.length]);

  const handleLayoutChange = useCallback(
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
    async (paletteId, dropPos = null) => {
      if (!current) return;
      const item = paletteItem(paletteId);
      const type = item?.type || paletteId;
      const config = defaultConfigFor(type, {
        title: item?.title,
        variant: item?.preview,
        paletteId: item?.id,
        upgrade: item?.upgrade || undefined,
        ...(item?.id === "device_table" || item?.preview === "table"
          ? {
              devicesPerPage: 10,
              defaultSortColumn: "name",
              defaultSortDirection: "asc",
              columns: [],
              selectedDeviceIds: "all",
            }
          : {}),
      });
      const grid = defaultLayoutFor(type, "new");
      delete grid.i;
      const w = Math.min(GRID_COLS, item?.layout?.w || grid.w || 3);
      const h = item?.layout?.h || grid.h || 2;

      let targetX = 0;
      let targetY = 0;

      if (dropPos && Number.isFinite(dropPos.x) && Number.isFinite(dropPos.y)) {
        targetX = Math.max(0, Math.min(GRID_COLS - w, dropPos.x));
        targetY = Math.max(0, dropPos.y);
      } else {
        for (const widget of widgets) {
          const wl = widget.layout || {};
          const bottom = (wl.y || 0) + (wl.h || 2);
          if (bottom > targetY) targetY = bottom;
        }
      }

      const action = await dispatch(
        addWidgetToDashboard({
          dashboardId: current.id,
          type,
          config,
          layout: { x: targetX, y: targetY, w, h },
        })
      );
      if (addWidgetToDashboard.fulfilled.match(action)) {
        // Do not open settings after drop, as requested by user
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

  const handleDuplicateWidget = useCallback(
    async (widget) => {
      if (!current || !widget) return;
      const layout = widget.layout || {};
      const action = await dispatch(
        addWidgetToDashboard({
          dashboardId: current.id,
          type: widget.type,
          config: { ...(widget.config || {}) },
          layout: {
            x: Math.max(0, Math.min(GRID_COLS - Math.min(GRID_COLS, layout.w || 3), layout.x || 0)),
            y: (layout.y || 0) + (layout.h || 2),
            w: Math.min(GRID_COLS, layout.w || 3),
            h: layout.h || 2,
          },
        })
      );
      if (addWidgetToDashboard.fulfilled.match(action)) {
        setConfigWidget(null);
        toast.success("Widget duplicated");
      } else {
        toast.error(action.payload?.message || "Failed to duplicate widget");
      }
    },
    [dispatch, current]
  );

  const handleDeleteWidget = useCallback(
    async (widget) => {
      if (!current) return;
      if (!window.confirm("Delete this widget?")) return;
      const action = await dispatch(
        removeWidget({ dashboardId: current.id, widgetId: widget.id })
      );
      if (removeWidget.fulfilled.match(action)) toast.success("Widget deleted");
      else toast.error(action.payload?.message || "Failed to delete widget");
    },
    [dispatch, current]
  );

  const handleRotateWidget = useCallback(
    (widget) => {
      if (!current || !widget) return;
      const layout = widget.layout || {};
      const curW = layout.w || 3;
      const curH = layout.h || 2;
      const newW = Math.max(1, Math.min(GRID_COLS, curH));
      const newH = Math.max(1, curW);
      const newX = Math.max(0, Math.min(GRID_COLS - newW, layout.x || 0));

      const config = widget.config || {};
      const changes = {
        layout: {
          ...layout,
          x: newX,
          w: newW,
          h: newH,
        },
      };

      if (config.levelPosition) {
        changes.config = {
          ...config,
          levelPosition: config.levelPosition === "vertical" ? "horizontal" : "vertical",
        };
      } else if (config.orientation) {
        changes.config = {
          ...config,
          orientation: config.orientation === "vertical" ? "horizontal" : "vertical",
        };
      }

      dispatch(
        saveWidget({
          dashboardId: current.id,
          widgetId: widget.id,
          changes,
        })
      );
      toast.success("Widget rotated");
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

  const orgLabel = useMemo(() => {
    const name = user?.organization_name || "My organization";
    const short = user?.org_id
      ? String(user.org_id).replace(/-/g, "").slice(-6).toUpperCase()
      : "";
    return short ? `${name} - ${short}` : name;
  }, [user]);

  const handleDuplicate = useCallback(async () => {
    if (!current) return;
    if (dashboards.length >= MAX_DASHBOARDS) {
      toast.error("Dashboard limit reached — upgrade for more");
      return;
    }
    const action = await dispatch(copyDashboard(current.id));
    if (copyDashboard.fulfilled.match(action)) {
      setEditing(false);
      if (isHomeRoute) {
        navigate("/dashboard", { state: { dashboardId: action.payload.id } });
      } else {
        setSelectedId(action.payload.id);
      }
      toast.success("Dashboard duplicated");
    } else {
      toast.error(action.payload?.message || "Failed to duplicate dashboard");
    }
  }, [dispatch, current, dashboards.length, isHomeRoute, navigate]);

  const handleSetHomepage = useCallback(async () => {
    if (!current || !user?.id) return;
    const action = await dispatch(
      markDashboardHomepage({ id: current.id, userId: user.id, enabled: true })
    );
    if (markDashboardHomepage.fulfilled.match(action)) {
      toast.success("Homepage updated");
    } else {
      toast.error(action.payload?.message || "Failed to set homepage");
    }
  }, [dispatch, current, user?.id]);

  const handleClearHomepage = useCallback(async () => {
    if (!current || !user?.id) return;
    const action = await dispatch(
      markDashboardHomepage({ id: current.id, userId: user.id, enabled: false })
    );
    if (markDashboardHomepage.fulfilled.match(action)) {
      toast.success("Homepage removed");
      if (isHomeRoute) navigate("/dashboard", { replace: true });
    } else {
      toast.error(action.payload?.message || "Failed to clear homepage");
    }
  }, [dispatch, current, user?.id, isHomeRoute, navigate]);

  const handleDeleteConfirm = useCallback(async () => {
    if (!current) return;
    const id = current.id;
    const action = await dispatch(removeDashboard(id));
    if (removeDashboard.fulfilled.match(action)) {
      const rest = dashboards.filter((item) => item.id !== id);
      setEditing(false);
      setDeleteOpen(false);
      if (isHomeRoute) navigate("/dashboard", { replace: true });
      else setSelectedId(rest[0]?.id || null);
      toast.success("Dashboard deleted");
    } else {
      toast.error(action.payload?.message || "Failed to delete dashboard");
    }
  }, [dispatch, current, dashboards, isHomeRoute, navigate]);

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
        toast.info("Command queued — device offline");
      } else {
        toast.success("Command sent");
      }
    } catch (err) {
      toast.error(extractApiError(err).message || "Failed to send command");
    }
  }, []);

  const loading = (status === "loading" || status === "idle") && dashboards.length === 0 && !editing;

  if (isHomeRoute && !homepageId && status === "succeeded") {
    return <Navigate to="/dashboard" replace />;
  }

  if (loading) {
    return (
      <div className="dash-shell flex min-h-[calc(100dvh-3.75rem)] items-center justify-center">
        <CircleNotch size={28} className="animate-spin text-primary" />
      </div>
    );
  }

  if (status === "failed" && dashboards.length === 0) {
    return (
      <div className="dash-shell flex min-h-[calc(100dvh-3.75rem)] items-center justify-center text-destructive">
        {error || "Failed to load dashboards"}
      </div>
    );
  }

  const inBuilder = editing && current;

  if (dashboards.length === 0 && !inBuilder) {
    return (
      <div className="dash-shell flex min-h-[calc(100dvh-3.75rem)] flex-col">
        <DashboardEmptyState onCreate={handleCreate} />
      </div>
    );
  }

  return (
    <div className={cn("dash-shell flex h-full min-h-0 overflow-hidden", inBuilder && "dash-shell-builder")}>
      {inBuilder ? (
        <div className="dash-builder-layout flex min-h-0 min-w-0 flex-1">
          <DashboardBuilderToolbox onAdd={handleAddWidget} className="hidden lg:flex" blynk />
          <div className="dash-builder-main flex min-w-0 flex-1 flex-col">
            <DashboardBuilderHeader
              name={editDraftName}
              onNameChange={setEditDraftName}
              onSave={handleSaveEdit}
              onCancel={handleCancelEdit}
              saving={saving}
            />
            <DashboardBuilderFilters
              sourceLabel={sourceLabel}
              onChangeSource={() => setSourceOpen(true)}
              timeRange={timeRange}
              onTimeRangeChange={(id) => persistSettings({ time_range: id })}
              onManageAccess={() => setAccessOpen(true)}
            />
            <div
              ref={canvasHostRef}
              className="dash-builder-body flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <DashboardBuilderToolbox onAdd={handleAddWidget} className="lg:hidden" blynk />
              <div className="flex min-h-0 flex-1 flex-col overflow-auto bg-slate-50/50">
                <DashboardCanvas
                  widgets={widgets}
                  editing
                  timeRange={timeRange}
                  onLayoutChange={handleLayoutChange}
                  onCommand={handleCommand}
                  onTogglePin={handleTogglePin}
                  onConfigure={setConfigWidget}
                  onDeleteWidget={handleDeleteWidget}
                  onDuplicateWidget={handleDuplicateWidget}
                  onRotateWidget={handleRotateWidget}
                  blynkGrid
                  onDropWidget={handleAddWidget}
                  className="min-h-full flex-1 min-w-[960px] w-full"
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <>
          {isHomeRoute ? null : (
            <DashboardListSidebar
              dashboards={dashboards}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setEditing(false);
              }}
              onCreate={handleCreate}
              maxDashboards={MAX_DASHBOARDS}
            />
          )}
          <div className="flex min-w-0 flex-1 flex-col">
            {current ? (
              <DashboardViewToolbar
                title={current.name}
                onEdit={() => setEditing(true)}
                onDuplicate={handleDuplicate}
                onManageAccess={() => setAccessOpen(true)}
                onSetHomepage={handleSetHomepage}
                onClearHomepage={handleClearHomepage}
                isHomepage={homepageId === current.id}
                onDelete={() => setDeleteOpen(true)}
                timeRange={timeRange}
                onTimeRangeChange={(id) => persistSettings({ time_range: id })}
                orgLabel={orgLabel}
              />
            ) : (
              <div className="flex flex-1 items-center justify-center text-muted-foreground">
                Select a dashboard
              </div>
            )}
            <div ref={canvasHostRef} className="dash-main flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 p-6">
                {current ? (
                  <DashboardCanvas
                    widgets={widgets}
                    editing={false}
                    timeRange={timeRange}
                    onLayoutChange={handleLayoutChange}
                    onCommand={handleCommand}
                    onTogglePin={handleTogglePin}
                    onConfigure={setConfigWidget}
                    onDeleteWidget={handleDeleteWidget}
                    onDuplicateWidget={handleDuplicateWidget}
                    onRotateWidget={handleRotateWidget}
                  />
                ) : null}
              </div>
            </div>
          </div>
        </>
      )}

      <WidgetSettingsDialog
        open={!!configWidget}
        widget={configWidget}
        devices={devices}
        onClose={() => setConfigWidget(null)}
        onSave={handleSaveConfig}
      />

      <DashboardDataSourceDialog
        open={sourceOpen}
        devices={devices}
        selectedIds={selectedDeviceIds}
        onClose={() => setSourceOpen(false)}
        onSave={(ids) => {
          persistSettings({
            org_scope: ids == null ? "all" : "selected",
            device_ids: ids,
          });
          setSourceOpen(false);
        }}
      />

      <DashboardAccessDrawer
        open={accessOpen}
        dashboardId={current?.id}
        onClose={() => setAccessOpen(false)}
      />

      <Dialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete dashboard"
        description="This removes the dashboard and every widget on it."
      >
        <DialogBody>
          <p className="text-sm text-muted-foreground">
            {current?.name ? `“${current.name}” will be deleted.` : "This dashboard will be deleted."}
          </p>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleDeleteConfirm}>
            Delete
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  );
}
