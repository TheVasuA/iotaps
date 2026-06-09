import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import uiReducer from "./uiSlice";
import devicesReducer from "./devicesSlice";
import dashboardsReducer from "./dashboardsSlice";
import rulesReducer from "./rulesSlice";
import notificationsReducer from "./notificationsSlice";

// Root Redux store. Feature slices (devices, dashboards, rules, billing,
// websocket cache) are registered here as their tasks land.
export const store = configureStore({
  reducer: {
    auth: authReducer,
    ui: uiReducer,
    devices: devicesReducer,
    dashboards: dashboardsReducer,
    rules: rulesReducer,
    notifications: notificationsReducer,
  },
});

export default store;
