import apiClient, { API_BASE_URL } from "@/lib/apiClient";

// Auth API surface (design.md "Auth" block). Each function maps 1:1 to a
// backend endpoint and returns the parsed response body. Token persistence and
// Redux dispatch are handled by callers (the auth pages / authSlice).

/** Decode a JWT payload without verifying the signature (client-side only). */
export function decodeJwt(token) {
  if (!token || typeof token !== "string") return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "="
    );
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/**
 * Build the Redux `user` principal from an access token (claims: sub, org_id,
 * role) plus any known email. Returns null when the token cannot be decoded.
 */
export function principalFromToken(accessToken, email) {
  const claims = decodeJwt(accessToken);
  if (!claims) return null;
  return {
    id: claims.sub,
    org_id: claims.org_id,
    role: claims.role,
    email: email || claims.email || null,
    account_type: claims.account_type || "individual",
    organization_name: claims.org_name || "",
  };
}

export async function register({
  email,
  password,
  referralCode,
  accountType = "individual",
  organizationName,
}) {
  const { data } = await apiClient.post("/auth/register", {
    email,
    password,
    referral_code: referralCode || null,
    account_type: accountType,
    organization_name: organizationName || null,
  });
  return data; // { user }
}

export async function login({ email, password, otp }) {
  const { data } = await apiClient.post("/auth/login", {
    email,
    password,
    ...(otp ? { otp } : {}),
  });
  return data; // { access_token, refresh_token, token_type }
}

export async function loginWithGoogle({ idToken, accountType, organizationName, otp }) {
  const { data } = await apiClient.post("/auth/oauth/google", {
    id_token: idToken,
    account_type: accountType || null,
    organization_name: organizationName || null,
    ...(otp ? { otp } : {}),
  });
  return data; // { access_token, refresh_token }
}

export async function logout({ refreshToken }) {
  if (!refreshToken) return;
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}

export async function requestPasswordReset({ email }) {
  const { data } = await apiClient.post("/auth/password/reset-request", { email });
  return data;
}

export async function confirmPasswordReset({ token, newPassword }) {
  await apiClient.post("/auth/password/reset", {
    token,
    new_password: newPassword,
  });
}

export async function enable2fa() {
  const { data } = await apiClient.post("/auth/2fa/enable");
  return data; // { secret, qr }
}

export async function verify2fa({ otp }) {
  const { data } = await apiClient.post("/auth/2fa/verify", { otp });
  return data;
}

/** Pull a human-readable message + error_code out of an axios error. */
export function extractApiError(err) {
  const body = err?.response?.data;
  if (body && typeof body === "object") {
    return {
      code: body.error_code || "error",
      message: body.message || "Something went wrong",
    };
  }
  if (err?.code === "ERR_NETWORK" || !err?.response) {
    const hint =
      typeof window !== "undefined"
        ? ` (${API_BASE_URL.replace(/^https?:\/\//, "")})`
        : "";
    return {
      code: "network_error",
      message: `Could not reach the server${hint}. Check your connection or try again in a moment.`,
    };
  }
  return { code: "network_error", message: "Could not reach the server" };
}
