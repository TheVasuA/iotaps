import apiClient from "@/lib/apiClient";

// Devices API surface (design.md "Devices" block, Req 5). Each function maps
// 1:1 to a backend endpoint under /api/v1/devices and returns the parsed body.
// Token handling and tenant scoping are applied by the shared apiClient and the
// backend middleware respectively.

/** List devices, optionally filtered by group and/or status. */
export async function listDevices({ groupId, status } = {}) {
  const params = {};
  if (groupId) params.group_id = groupId;
  if (status) params.status = status;
  const { data } = await apiClient.get("/devices", { params });
  return data; // [device]
}

/** Fetch a single device by id. */
export async function getDevice(id) {
  const { data } = await apiClient.get(`/devices/${id}`);
  return data.device; // { device } -> device
}

/**
 * Provision a new device. Returns { device, mqtt_credentials, qr }; the
 * credential secret is present exactly once here and never again (Req 5.1).
 */
export async function createDevice({ label, groupId, templateId, deviceUid } = {}) {
  const { data } = await apiClient.post("/devices", {
    label: label || null,
    group_id: groupId || null,
    template_id: templateId || null,
    device_uid: deviceUid || null,
  });
  return data; // { device, mqtt_credentials, qr }
}

/** Update a device's label, group, and/or maintenance flag (Req 5.3-5.5, 5.7). */
export async function updateDevice(id, changes) {
  const body = {};
  if ("label" in changes) body.label = changes.label;
  if ("groupId" in changes) body.group_id = changes.groupId;
  if ("maintenanceMode" in changes) body.maintenance_mode = changes.maintenanceMode;
  const { data } = await apiClient.patch(`/devices/${id}`, body);
  return data.device;
}

/** Delete a device and revoke its MQTT credentials (Req 5.9). */
export async function deleteDevice(id) {
  await apiClient.delete(`/devices/${id}`);
}

/** Assign a device to a Device_User, granting access to it only (Req 5.6). */
export async function assignDevice(id, userId) {
  await apiClient.post(`/devices/${id}/assign`, { user_id: userId });
}

/** Create a device group (Req 5.5). */
export async function createGroup(name) {
  const { data } = await apiClient.post("/devices/groups", { name });
  return data.group; // { group } -> group
}

/** List device groups in the caller's organization (Req 5.5). */
export async function listGroups() {
  const { data } = await apiClient.get("/devices/groups");
  return data; // [group]
}

/**
 * Fetch the QR PNG for a device as an object URL the caller can use as an
 * <img> src. The caller is responsible for revoking the URL when done.
 */
export async function fetchDeviceQrUrl(id) {
  const { data } = await apiClient.get(`/devices/${id}/qr`, {
    responseType: "blob",
  });
  return URL.createObjectURL(data);
}
