import apiClient from "@/lib/apiClient";

// Telemetry API surface (design.md "Telemetry & Reports", Req 6.6). Maps to the
// backend endpoints under /api/v1/devices/{id}/telemetry.

/** Fetch telemetry points for a device at a given resolution. */
export async function getTelemetry(deviceId, { resolution = "raw", from, to, limit } = {}) {
  const params = { resolution };
  if (from) params.from = from;
  if (to) params.to = to;
  if (limit) params.limit = limit;
  const { data } = await apiClient.get(`/devices/${deviceId}/telemetry`, { params });
  return data;
}

/**
 * Download a device's telemetry as a CSV file. Fetches with the auth token,
 * builds a Blob, and triggers a browser download.
 */
export async function exportTelemetryCsv(deviceId, { resolution = "raw", from, to } = {}) {
  const params = { resolution };
  if (from) params.from = from;
  if (to) params.to = to;
  const response = await apiClient.get(`/devices/${deviceId}/telemetry/export`, {
    params,
    responseType: "blob",
  });
  const blob = new Blob([response.data], { type: "text/csv" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `telemetry_${deviceId}_${resolution}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
