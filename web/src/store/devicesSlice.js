import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import {
  listDevices,
  createDevice,
  updateDevice,
  deleteDevice,
  assignDevice,
  createGroup,
} from "@/lib/devicesApi";
import { extractApiError } from "@/lib/authApi";

// Devices slice: owns the fleet list, device groups, the active status/group
// filters, and request status for the device management UI (task 4.5, Req 5).
// Async thunks wrap the devicesApi calls; reducers keep the cached list in sync
// so views update without an extra round trip.

const initialState = {
  items: [], // [device]
  groups: [], // [group]
  filters: { groupId: null, status: null },
  status: "idle", // idle | loading | succeeded | failed
  error: null,
};

export const fetchDevices = createAsyncThunk(
  "devices/fetch",
  async (filters, { rejectWithValue }) => {
    try {
      return await listDevices(filters || {});
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const provisionDevice = createAsyncThunk(
  "devices/provision",
  async (payload, { rejectWithValue }) => {
    try {
      return await createDevice(payload);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const saveDevice = createAsyncThunk(
  "devices/save",
  async ({ id, changes }, { rejectWithValue }) => {
    try {
      return await updateDevice(id, changes);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const removeDevice = createAsyncThunk(
  "devices/remove",
  async (id, { rejectWithValue }) => {
    try {
      await deleteDevice(id);
      return id;
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const assignDeviceToUser = createAsyncThunk(
  "devices/assign",
  async ({ id, userId }, { rejectWithValue }) => {
    try {
      await assignDevice(id, userId);
      return { id, userId };
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

export const createDeviceGroup = createAsyncThunk(
  "devices/createGroup",
  async (name, { rejectWithValue }) => {
    try {
      return await createGroup(name);
    } catch (err) {
      return rejectWithValue(extractApiError(err));
    }
  }
);

const devicesSlice = createSlice({
  name: "devices",
  initialState,
  reducers: {
    setFilters(state, action) {
      state.filters = { ...state.filters, ...action.payload };
    },
    // Replace/insert a single device in the cache (e.g. after provisioning).
    upsertDevice(state, action) {
      const device = action.payload;
      const idx = state.items.findIndex((d) => d.id === device.id);
      if (idx >= 0) state.items[idx] = device;
      else state.items.unshift(device);
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchDevices.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchDevices.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchDevices.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload?.message || "Failed to load devices";
      })
      .addCase(provisionDevice.fulfilled, (state, action) => {
        state.items.unshift(action.payload.device);
      })
      .addCase(saveDevice.fulfilled, (state, action) => {
        const idx = state.items.findIndex((d) => d.id === action.payload.id);
        if (idx >= 0) state.items[idx] = action.payload;
      })
      .addCase(removeDevice.fulfilled, (state, action) => {
        state.items = state.items.filter((d) => d.id !== action.payload);
      })
      .addCase(createDeviceGroup.fulfilled, (state, action) => {
        state.groups.push(action.payload);
      });
  },
});

export const { setFilters, upsertDevice } = devicesSlice.actions;
export default devicesSlice.reducer;

// Selectors
export const selectDevices = (s) => s.devices.items;
export const selectDeviceGroups = (s) => s.devices.groups;
export const selectDeviceFilters = (s) => s.devices.filters;
export const selectDevicesStatus = (s) => s.devices.status;
export const selectDevicesError = (s) => s.devices.error;
export const selectDeviceById = (id) => (s) =>
  s.devices.items.find((d) => d.id === id) || null;
