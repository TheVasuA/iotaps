import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import App from "./App";
import store from "./store";
import { initTheme } from "@/lib/theme";
import { selectRole, setCredentials, logout } from "./store/authSlice";
import { tokenStore } from "@/lib/apiClient";
import { principalFromToken, decodeJwt } from "@/lib/authApi";
import "./styles/index.css";

// Restore the session from a persisted access token so a page reload keeps the
// user signed in and re-applies their role theme (Req 4.1-4.3). Expired tokens
// are cleared; the refresh interceptor handles renewal on the next API call.
function bootstrapSession() {
  const access = tokenStore.getAccess();
  if (!access) return;
  const claims = decodeJwt(access);
  if (!claims) {
    tokenStore.clear();
    return;
  }
  // Drop tokens that are already fully expired (no refresh possible offline).
  if (claims.exp && claims.exp * 1000 < Date.now() && !tokenStore.getRefresh()) {
    store.dispatch(logout());
    return;
  }
  const user = principalFromToken(access);
  if (user) {
    store.dispatch(setCredentials({ user }));
  }
}

bootstrapSession();

// Apply theming groundwork before first paint (Req 4.1-4.4): set the role
// theme (from any restored session) and the persisted light/dark mode.
initTheme(selectRole(store.getState()));

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </React.StrictMode>
);
