import apiClient from "@/lib/apiClient";

// Commands API surface (design.md "Commands" block, Req 9). Each function maps
// 1:1 to a backend endpoint under /api/v1/devices/{id}/commands and returns the
// parsed body. Token handling and tenant/device-access scoping are applied by
// the shared apiClient and the backend middleware respectively (Req 2.4, 3.x).

/**
 * Issue a control command to a device (Req 9.1 ON/OFF, 9.2 slider value).
 *
 * @param {string} deviceId
 * @param {{ type: "on"|"off"|"value", value?: number, target?: string }} command
 * @returns {Promise<{command_id, device_id, type, value, status, created_at, updated_at}>}
 *   The response carries the initial status: SENT when the device is online or
 *   QUEUED when it is offline. CONFIRMED/UNACKNOWLEDGED arrive later over the
 *   WebSocket command_status channel (Req 9.4, 9.7).
 */
export async function issueCommand(deviceId, { type, value, target } = {}) {
  const body = { type };
  if (value !== undefined && value !== null) body.value = value;
  if (target) body.target = target;
  const { data } = await apiClient.post(`/devices/${deviceId}/commands`, body);
  return data;
}

/** Fetch a command's current status (Req 9.4-9.7). */
export async function getCommandStatus(deviceId, commandId) {
  const { data } = await apiClient.get(
    `/devices/${deviceId}/commands/${commandId}`
  );
  return data;
}
