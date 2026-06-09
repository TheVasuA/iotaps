import axios from "axios";

// Centralized API client for the IoTAPS REST API (design: /api/v1).
//
// Responsibilities:
//   - base URL + JSON defaults
//   - attach the JWT access token to outgoing requests
//   - on 401, attempt a single refresh via /auth/refresh and replay the request
//
// Token storage is abstracted behind a small token store so the auth slice can
// own the source of truth later (task 2.8). For the shell we use localStorage.

const ACCESS_KEY = "iotaps.auth.access";
const REFRESH_KEY = "iotaps.auth.refresh";

export const tokenStore = {
  getAccess: () => {
    try {
      return localStorage.getItem(ACCESS_KEY);
    } catch {
      return null;
    }
  },
  getRefresh: () => {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  set: (access, refresh) => {
    try {
      if (access) localStorage.setItem(ACCESS_KEY, access);
      if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    } catch {
      /* storage unavailable - tokens remain in-memory only */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* noop */
    }
  },
};

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Single-flight refresh: queue concurrent 401s behind one refresh call.
let refreshPromise = null;

async function refreshAccessToken() {
  const refresh = tokenStore.getRefresh();
  if (!refresh) throw new Error("no_refresh_token");
  // Use a bare axios call to avoid recursive interceptors.
  const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
    refresh_token: refresh,
  });
  tokenStore.set(data.access_token, data.refresh_token);
  return data.access_token;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const { response, config } = error;
    if (!response || response.status !== 401 || config?._retried) {
      return Promise.reject(error);
    }
    config._retried = true;
    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const newToken = await refreshPromise;
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${newToken}`;
      return apiClient(config);
    } catch (refreshErr) {
      tokenStore.clear();
      return Promise.reject(refreshErr);
    }
  }
);

export default apiClient;
