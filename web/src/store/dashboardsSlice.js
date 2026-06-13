import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import {
  listDashboards,
  createDashboard,
  getDashboard,
  updateDashboard,
  addWidget,
  updateWidget,
  deleteDashboard,
  deleteWidget,
} from "@/lib/dashboardsApi";
import { appendPoint, readMetric } from "@/lib/widgets";
import { extractApiError } from "@/lib/authApi";

// Dashboards slice (Task 8.2, Req 7): owns the dashboard list, the active
// dashboard + its widgets, and the websocket telemetry cache that widgets bind
// to. Telemetry frames arriving over the WebSocket are reduced here (via
// `telemetryReceived`) so any number of widgets can read the same device's
// latest value / chart series without duplicating socket handling.

const MAX_SERIES_POINTS = 1000; // ring-buffer cap per (device, metric).

const initialState = {
  items: [], // [dashboard] (list view)
  current: null, // active dashboard { id, name, layout, ... }
  widgets: [], // widgets of the active dashboard
  status: "idle", // idle | loading | succeeded | failed
  saving: false,
  error: null,
  // Telemetry cache keyed by device id:
  //   latest[deviceId] = { ts, data }
  //   series[deviceId][metric] = [{ ts, value }]
  latest: {},
  series: {},
};

export const fetchDashboards = createAsyncThunk(
  "dashboards/fetchAll",
  async (_, { rejectWithValue }) => {
    try {
      return await listDashboards();
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const fetchDashboard = createAsyncThunk(
  "dashboards/fetchOne",
  async (id, { rejectWithValue }) => {
    try {
      return await getDashboard(id);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const createNewDashboard = createAsyncThunk(
  "dashboards/create",
  async ({ name, layout }, { rejectWithValue }) => {
    try {
      return await createDashboard({ name, layout });
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const saveLayout = createAsyncThunk(
  "dashboards/saveLayout",
  async ({ id, layout }, { rejectWithValue }) => {
    try {
      return await updateDashboard(id, { layout });
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const addWidgetToDashboard = createAsyncThunk(
  "dashboards/addWidget",
  async ({ dashboardId, type, config, layout }, { rejectWithValue }) => {
    try {
      return await addWidget(dashboardId, { type, config, layout });
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const saveWidget = createAsyncThunk(
  "dashboards/saveWidget",
  async ({ dashboardId, widgetId, changes }, { rejectWithValue }) => {
    try {
      return await updateWidget(dashboardId, widgetId, changes);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const removeDashboard = createAsyncThunk(
  "dashboards/delete",
  async (id, { rejectWithValue }) => {
    try {
      await deleteDashboard(id);
      return id;
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const removeWidget = createAsyncThunk(
  "dashboards/deleteWidget",
  async ({ dashboardId, widgetId }, { rejectWithValue }) => {
    try {
      await deleteWidget(dashboardId, widgetId);
      return widgetId;
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

const dashboardsSlice = createSlice({
  name: "dashboards",
  initialState,
  reducers: {
    // Reduce a telemetry frame from the WebSocket into the cache so bound
    // widgets re-render with the new values (Req 7.4). `metrics` (optional)
    // limits which metrics get a series ring-buffer; when omitted, every
    // numeric metric in the frame is tracked.
    telemetryReceived(state, action) {
      const { deviceId, ts, data, metrics } = action.payload;
      if (!deviceId || !data) return;
      state.latest[deviceId] = { ts, data };
      const wanted =
        Array.isArray(metrics) && metrics.length
          ? metrics
          : Object.keys(data);
      if (!state.series[deviceId]) state.series[deviceId] = {};
      for (const metric of wanted) {
        const value = readMetric(data, metric);
        if (value == null) continue;
        const prev = state.series[deviceId][metric] || [];
        state.series[deviceId][metric] = appendPoint(
          prev,
          { ts, value },
          MAX_SERIES_POINTS
        );
      }
    },
    // Seed a chart widget's series from a historical telemetry query so charts
    // are populated before the first live frame arrives.
    seedSeries(state, action) {
      const { deviceId, metric, points } = action.payload;
      if (!deviceId || !metric || !Array.isArray(points)) return;
      if (!state.series[deviceId]) state.series[deviceId] = {};
      const trimmed = points.slice(-MAX_SERIES_POINTS);
      state.series[deviceId][metric] = trimmed;
    },
    clearTelemetry(state) {
      state.latest = {};
      state.series = {};
    },
    // Reset all dashboard state (called on logout to prevent data leaking between users)
    resetDashboards() {
      return initialState;
    },
    // Optimistically apply a layout to the active dashboard (drag/resize) so
    // the canvas reflects the change immediately; persisted via saveLayout.
    setCurrentLayout(state, action) {
      if (state.current) state.current.layout = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchDashboards.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchDashboards.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
        // Clear active dashboard + widgets when the list changes (e.g. new user session)
        if (action.payload.length === 0) {
          state.current = null;
          state.widgets = [];
        }
      })
      .addCase(fetchDashboards.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload?.message || "Failed to load dashboards";
      })
      .addCase(fetchDashboard.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchDashboard.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.current = action.payload.dashboard;
        state.widgets = action.payload.widgets;
      })
      .addCase(fetchDashboard.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload?.message || "Failed to load dashboard";
      })
      .addCase(createNewDashboard.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
      })
      .addCase(saveLayout.pending, (state) => {
        state.saving = true;
      })
      .addCase(saveLayout.fulfilled, (state, action) => {
        state.saving = false;
        if (state.current && state.current.id === action.payload.id) {
          state.current.layout = action.payload.layout;
        }
      })
      .addCase(saveLayout.rejected, (state, action) => {
        state.saving = false;
        state.error = action.payload?.message || "Failed to save layout";
      })
      .addCase(addWidgetToDashboard.fulfilled, (state, action) => {
        state.widgets.push(action.payload);
      })
      .addCase(saveWidget.fulfilled, (state, action) => {
        const idx = state.widgets.findIndex((w) => w.id === action.payload.id);
        if (idx >= 0) state.widgets[idx] = action.payload;
      })
      .addCase(removeDashboard.fulfilled, (state, action) => {
        state.items = state.items.filter((d) => d.id !== action.payload);
        if (state.current && state.current.id === action.payload) {
          state.current = null;
          state.widgets = [];
        }
      })
      .addCase(removeWidget.fulfilled, (state, action) => {
        state.widgets = state.widgets.filter((w) => w.id !== action.payload);
      });
  },
});

export const {
  telemetryReceived,
  seedSeries,
  clearTelemetry,
  resetDashboards,
  setCurrentLayout,
} = dashboardsSlice.actions;
export default dashboardsSlice.reducer;

// Selectors
export const selectDashboards = (s) => s.dashboards.items;
export const selectCurrentDashboard = (s) => s.dashboards.current;
export const selectWidgets = (s) => s.dashboards.widgets;
export const selectDashboardsStatus = (s) => s.dashboards.status;
export const selectDashboardsError = (s) => s.dashboards.error;
export const selectDashboardSaving = (s) => s.dashboards.saving;
export const selectLatest = (deviceId) => (s) =>
  deviceId ? s.dashboards.latest[deviceId] || null : null;
export const selectSeries = (deviceId, metric) => (s) =>
  deviceId && metric ? s.dashboards.series[deviceId]?.[metric] || [] : [];
