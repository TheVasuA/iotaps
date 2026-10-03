import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import App from "./App";
import store from "./store";
import { initTheme } from "@/lib/theme";
import { selectRole, setCredentials, logout } from "./store/authSlice";
import { tokenStore } from "@/lib/apiClient";
import { principalFromToken, decodeJwt } from "@/lib/authApi";
import { refreshSessionIfExpired } from "@/lib/sessionRefresh";
import "./styles/index.css";

function bootstrapSessionFromStorage() {
  const access = tokenStore.getAccess();
  if (!access) return;
  const claims = decodeJwt(access);
  if (!claims) {
    tokenStore.clear();
    return;
  }
  if (claims.exp && claims.exp * 1000 < Date.now() && !tokenStore.getRefresh()) {
    store.dispatch(logout());
    return;
  }
  const user = principalFromToken(access);
  if (user) {
    store.dispatch(setCredentials({ user }));
  }
}

async function bootstrapApp() {
  bootstrapSessionFromStorage();
  const refreshed = await refreshSessionIfExpired();
  if (refreshed?.user) {
    store.dispatch(setCredentials(refreshed));
  }
  initTheme(selectRole(store.getState()));

  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <Provider store={store}>
        <App />
      </Provider>
    </React.StrictMode>
  );
}

bootstrapApp();
