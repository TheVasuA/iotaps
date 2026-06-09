// Command ACK feedback mapping (Task 9.3, Req 9.1, 9.2, 9.4).
//
// Pure helpers that translate a command status into the Sonner toast that the
// control widgets surface to the user. Kept free of React/Sonner so the mapping
// can be unit- and property-tested in isolation, and so the widgets and any
// future notification surface share one source of truth.
//
// Status lifecycle (design "Command Flow", mirrored by the backend
// CommandStatus enum in app/services/command_service.py):
//
//   SENT           published to the device, awaiting ACK   -> "info"  (pending)
//   QUEUED         device offline, command queued          -> "info"  (pending)
//   CONFIRMED      device acknowledged the command         -> "success"
//   UNACKNOWLEDGED no ACK within the timeout window         -> "error"
//
// CONFIRMED and UNACKNOWLEDGED are terminal (Req 9.4, 9.7); SENT and QUEUED are
// transient and resolve to one of the terminal states over the WebSocket
// command_status channel.

export const COMMAND_STATUS = Object.freeze({
  SENT: "SENT",
  QUEUED: "QUEUED",
  CONFIRMED: "CONFIRMED",
  UNACKNOWLEDGED: "UNACKNOWLEDGED",
});

// Sonner toast variants we drive. "loading" lets a pending toast be promoted
// in place once the terminal status arrives (toast.success(..., { id })).
export const TOAST_VARIANT = Object.freeze({
  LOADING: "loading",
  SUCCESS: "success",
  ERROR: "error",
  INFO: "info",
});

// Statuses that will not change again (Req 9.4 CONFIRMED, Req 9.7 UNACKNOWLEDGED).
const TERMINAL = new Set([
  COMMAND_STATUS.CONFIRMED,
  COMMAND_STATUS.UNACKNOWLEDGED,
]);

/** Whether a status is terminal (no further command_status update expected). */
export function isTerminalStatus(status) {
  return TERMINAL.has(status);
}

/** Human label for the command issued, e.g. "Turn on", "Turn off", "Set to 128". */
export function describeCommand({ type, value } = {}) {
  if (type === "on") return "Turn on";
  if (type === "off") return "Turn off";
  if (type === "value") return `Set to ${value}`;
  return "Command";
}

/**
 * Map a command status to the toast that should be shown for it.
 *
 * @param {string} status one of COMMAND_STATUS
 * @param {{ type?: string, value?: number, deviceLabel?: string }} [ctx]
 * @returns {{ variant: string, message: string, description?: string }|null}
 *   null for an unrecognised status (caller shows nothing).
 */
export function feedbackForStatus(status, ctx = {}) {
  const subject = ctx.deviceLabel ? `${ctx.deviceLabel}: ` : "";
  const action = describeCommand(ctx);
  switch (status) {
    case COMMAND_STATUS.SENT:
      return {
        variant: TOAST_VARIANT.LOADING,
        message: `${subject}${action} sent`,
        description: "Waiting for the device to confirm…",
      };
    case COMMAND_STATUS.QUEUED:
      return {
        variant: TOAST_VARIANT.LOADING,
        message: `${subject}${action} queued`,
        description: "Device is offline; it will run on reconnect.",
      };
    case COMMAND_STATUS.CONFIRMED:
      return {
        variant: TOAST_VARIANT.SUCCESS,
        message: `${subject}${action} confirmed`,
        description: "The device acknowledged the command.",
      };
    case COMMAND_STATUS.UNACKNOWLEDGED:
      return {
        variant: TOAST_VARIANT.ERROR,
        message: `${subject}${action} unacknowledged`,
        description: "No response from the device in time.",
      };
    default:
      return null;
  }
}
