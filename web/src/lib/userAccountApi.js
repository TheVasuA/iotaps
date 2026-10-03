import apiClient from "@/lib/apiClient";

export async function getProfile() {
  const { data } = await apiClient.get("/auth/me");
  return data;
}

export async function updateProfile(body) {
  const { data } = await apiClient.patch("/auth/me", body);
  return data;
}

export async function changePassword({ currentPassword, newPassword }) {
  await apiClient.post("/auth/password/change", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

export async function get2faStatus() {
  const { data } = await apiClient.get("/auth/2fa/status");
  return data;
}

export async function enable2fa() {
  const { data } = await apiClient.post("/auth/2fa/enable");
  return data;
}

export async function verify2fa({ otp }) {
  const { data } = await apiClient.post("/auth/2fa/verify", { otp });
  return data;
}

export async function disable2fa({ password, otp }) {
  await apiClient.post("/auth/2fa/disable", { password, otp });
}

export async function regenerateBackupCodes({ password, otp }) {
  const { data } = await apiClient.post("/auth/2fa/backup-codes/regenerate", {
    password,
    otp,
  });
  return data;
}

export async function linkGoogleAccount({ idToken }) {
  const { data } = await apiClient.post("/auth/oauth/google/link", {
    id_token: idToken,
  });
  return data;
}

export async function unlinkGoogleAccount({ password }) {
  const { data } = await apiClient.post("/auth/oauth/google/unlink", { password });
  return data;
}

export async function setInitialPassword({ newPassword }) {
  await apiClient.post("/auth/password/set", { new_password: newPassword });
}
