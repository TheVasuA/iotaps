import apiClient from "@/lib/apiClient";

// Dashboards & Widgets API surface (design.md "Dashboards & Widgets", Req 7, 8).
// Each function maps 1:1 to a backend endpoint under /api/v1/dashboards and
// returns the parsed body. Token handling and tenant scoping are applied by the
// shared apiClient and the backend middleware respectively.

/** List dashboards in the caller's organization. */
export async function listDashboards() {
  const { data } = await apiClient.get("/dashboards");
  return data; // [dashboard]
}

/** Create a dashboard. Optionally seed the React Grid Layout. */
export async function createDashboard({ name, layout } = {}) {
  const { data } = await apiClient.post("/dashboards", {
    name,
    layout: layout || null,
  });
  return data.dashboard; // { dashboard } -> dashboard
}

/** Fetch a dashboard and its widgets. */
export async function getDashboard(id) {
  const { data } = await apiClient.get(`/dashboards/${id}`);
  return data; // { dashboard, widgets }
}

/**
 * Rename and/or persist the grid layout for a dashboard (Req 7.1, 7.2). Only
 * the keys present in `changes` are sent so a layout save does not clobber the
 * name and vice versa.
 */
export async function updateDashboard(id, changes = {}) {
  const body = {};
  if ("name" in changes) body.name = changes.name;
  if ("layout" in changes) body.layout = changes.layout;
  const { data } = await apiClient.patch(`/dashboards/${id}`, body);
  return data.dashboard;
}

/** Add a widget to a dashboard, placing it on the canvas (Req 7.1, 7.3). */
export async function addWidget(dashboardId, { type, config, layout } = {}) {
  const { data } = await apiClient.post(`/dashboards/${dashboardId}/widgets`, {
    type,
    config: config || null,
    layout: layout || null,
  });
  return data.widget; // { widget } -> widget
}

/**
 * Update a widget's config, layout, pinned state, or annotations
 * (Req 7.2, 7.5, 7.6). Only the provided keys are sent.
 */
export async function updateWidget(dashboardId, widgetId, changes = {}) {
  const body = {};
  if ("config" in changes) body.config = changes.config;
  if ("layout" in changes) body.layout = changes.layout;
  if ("pinned" in changes) body.pinned = changes.pinned;
  if ("annotations" in changes) body.annotations = changes.annotations;
  const { data } = await apiClient.patch(
    `/dashboards/${dashboardId}/widgets/${widgetId}`,
    body
  );
  return data.widget;
}

/** Enable a read-only public link for a dashboard (Req 8.1). */
export async function shareDashboard(id) {
  const { data } = await apiClient.post(`/dashboards/${id}/share`);
  return data; // { public_token, url }
}

/** Revoke a dashboard's public link (Req 8.3). */
export async function unshareDashboard(id) {
  await apiClient.delete(`/dashboards/${id}/share`);
}

/** Delete a dashboard and all its widgets. */
export async function deleteDashboard(id) {
  await apiClient.delete(`/dashboards/${id}`);
}

/** Delete a single widget from a dashboard. */
export async function deleteWidget(dashboardId, widgetId) {
  await apiClient.delete(`/dashboards/${dashboardId}/widgets/${widgetId}`);
}
