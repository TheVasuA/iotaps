import { createSlice } from "@reduxjs/toolkit";

// UI slice: ephemeral, non-domain UI state (sidebar, modals). Domain slices
// (devices, dashboards, websocket cache) are added in their respective tasks.
const initialState = {
  sidebarOpen: true,
};

const uiSlice = createSlice({
  name: "ui",
  initialState,
  reducers: {
    toggleSidebar(state) {
      state.sidebarOpen = !state.sidebarOpen;
    },
    setSidebarOpen(state, action) {
      state.sidebarOpen = Boolean(action.payload);
    },
  },
});

export const { toggleSidebar, setSidebarOpen } = uiSlice.actions;
export default uiSlice.reducer;

export const selectSidebarOpen = (s) => s.ui.sidebarOpen;
