import { createSlice } from "@reduxjs/toolkit";
import {
  initTheme,
  applyRoleTheme,
  setVisualMode,
  loadPersistedMode,
  themeForRole,
} from "@/lib/theme";
import { tokenStore } from "@/lib/apiClient";
import { logout as logoutApi } from "@/lib/authApi";

// Auth slice: owns the authenticated principal (id, org_id, role) and the
// active visual theme. Role drives the role theme (Req 4.1-4.3); mode drives
// light/dark (Req 4.4). Login/2FA/OAuth flows are built in task 2.8 - this
// shell only wires the state shape and theme side effects.

const initialState = {
  user: null, // { id, email, org_id, role }
  status: "anonymous", // anonymous | authenticated
  theme: themeForRole(undefined),
  mode: loadPersistedMode(),
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setCredentials(state, action) {
      const { user, accessToken, refreshToken } = action.payload;
      state.user = user;
      state.status = "authenticated";
      state.theme = themeForRole(user?.role);
      if (accessToken) tokenStore.set(accessToken, refreshToken);
      // Apply the role theme + persisted mode together on login.
      initTheme(user?.role);
    },
    logout(state) {
      state.user = null;
      state.status = "anonymous";
      state.theme = themeForRole(undefined);
      tokenStore.clear();
      applyRoleTheme(undefined);
    },
    // Toggle/set light-dark mode with Req 4.4 fail-without-persist semantics.
    setMode(state, action) {
      const result = setVisualMode(action.payload);
      // Only update state.mode when the apply (and thus persist) succeeded.
      if (result.ok) {
        state.mode = result.mode;
      }
    },
  },
});

export const { setCredentials, logout, setMode } = authSlice.actions;
export default authSlice.reducer;

// Thunk: revoke the refresh token server-side (Req 1.6) then clear local state.
// Logout proceeds even if the network call fails so the user is never stuck.
export const logoutAndRevoke = () => async (dispatch) => {
  const refreshToken = tokenStore.getRefresh();
  try {
    await logoutApi({ refreshToken });
  } catch {
    /* best-effort revocation; clear local state regardless */
  }
  dispatch(logout());
};

// Selectors
export const selectUser = (s) => s.auth.user;
export const selectIsAuthenticated = (s) => s.auth.status === "authenticated";
export const selectRole = (s) => s.auth.user?.role || null;
export const selectTheme = (s) => s.auth.theme;
export const selectMode = (s) => s.auth.mode;
