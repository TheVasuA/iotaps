import apiClient from "@/lib/apiClient";

// Support chat API surface (Task 19.7, Req 21.1, 21.2, 21.3). Maps 1:1 to the
// backend endpoints under /api/v1/support and returns the parsed body. Token
// handling and tenant scoping are applied by the shared apiClient and the
// backend middleware.
//
// Conversation model (app/api/v1/support.py): a Device_User sends a message
// about one of their assigned devices; it is delivered to the Project_Center
// the device is assigned to, carrying the device identity (Req 21.1, 21.2). A
// Project_Center replies to a message and the reply is routed back to the
// originating Device_User (Req 21.3).

/**
 * List support messages visible to the caller, optionally filtered to a single
 * device's thread (Req 21.1, 21.3).
 *
 * @param {{ deviceId?: string }} [params]
 * @returns {Promise<Array<{
 *   id: string, org_id: string, device_id: string|null,
 *   device_user_id: string|null, project_center_id: string|null,
 *   message: string, sender_role: string|null, created_at: string|null
 * }>>}
 */
export async function listSupportMessages({ deviceId } = {}) {
  const params = {};
  if (deviceId) params.device_id = deviceId;
  const { data } = await apiClient.get("/support/messages", { params });
  return data; // [message]
}

/**
 * Send a Device_User support message about an assigned device. The backend
 * routes it to the device's Project_Center with the device identity (Req 21.1,
 * 21.2).
 *
 * @param {{ deviceId: string, message: string }} input
 * @returns {Promise<object>} the created message
 */
export async function sendSupportMessage({ deviceId, message }) {
  const { data } = await apiClient.post("/support/messages", {
    device_id: deviceId,
    message,
  });
  return data.message; // { message } -> message
}

/**
 * Reply to a support message as a Project_Center; the reply is delivered to the
 * originating Device_User (Req 21.3).
 *
 * @param {string} messageId the id of the message being replied to
 * @param {string} message the reply text
 * @returns {Promise<object>} the created reply message
 */
export async function replySupportMessage(messageId, message) {
  const { data } = await apiClient.post(
    `/support/messages/${messageId}/reply`,
    { message }
  );
  return data.message; // { message } -> message
}
