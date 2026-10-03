import axios from "axios";
import { API_BASE_URL, tokenStore } from "@/lib/apiClient";
import { decodeJwt, principalFromToken } from "@/lib/authApi";

/**
 * Rotate refresh token and persist tokens. Returns the new access token.
 * Used by the API client interceptor and admin role gate.
 */
export async function refreshAccessToken() {
  const refresh = tokenStore.getRefresh();
  if (!refresh) throw new Error("no_refresh_token");
  const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
    refresh_token: refresh,
  });
  const access = data.access_token;
  const newRefresh = data.refresh_token || refresh;
  tokenStore.set(access, newRefresh);
  await syncStoreFromAccessToken(access);
  return access;
}

export function applySessionFromAccessToken(accessToken, refreshToken) {
  const user = principalFromToken(accessToken);
  return { user, accessToken, refreshToken: refreshToken ?? tokenStore.getRefresh() };
}

/** Update Redux after token rotation (dynamic import avoids apiClient ↔ store cycle). */
export async function syncStoreFromAccessToken(accessToken) {
  const user = principalFromToken(accessToken);
  if (!user) return;
  const { default: store } = await import("@/store");
  const { setCredentials } = await import("@/store/authSlice");
  store.dispatch(
    setCredentials({
      user,
      accessToken,
      refreshToken: tokenStore.getRefresh(),
    })
  );
}

/** Proactive refresh when the access JWT is expired but a refresh token exists. */
export async function refreshSessionIfExpired() {
  const access = tokenStore.getAccess();
  const refresh = tokenStore.getRefresh();
  if (!access || !refresh) return null;

  const claims = decodeJwt(access);
  if (!claims) {
    tokenStore.clear();
    return null;
  }

  const expMs = claims.exp ? claims.exp * 1000 : 0;
  if (expMs > Date.now() + 15_000) {
    return applySessionFromAccessToken(access, refresh);
  }

  try {
    const newAccess = await refreshAccessToken();
    return applySessionFromAccessToken(newAccess);
  } catch {
    tokenStore.clear();
    return null;
  }
}
