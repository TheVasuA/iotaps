import { useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";
import { issueCommand } from "@/lib/commandsApi";
import realtimeClient from "@/lib/realtime";
import { extractApiError } from "@/lib/authApi";
import {
  feedbackForStatus,
  isTerminalStatus,
  TOAST_VARIANT,
  COMMAND_STATUS,
} from "@/lib/commandFeedback";

// useDeviceCommand (Task 9.3, Req 9.1, 9.2, 9.4): a small hook the control
// widgets use to issue a command and surface Sonner ACK feedback.
//
// Flow:
//   1. POST the command. The response carries the initial status (SENT when the
//      device is online, QUEUED when offline) -> a pending/loading toast.
//   2. Subscribe to the device's WebSocket channel and watch for the
//      command_status message matching this command_id. CONFIRMED promotes the
//      toast to success (Req 9.4); UNACKNOWLEDGED promotes it to an error
//      (Req 9.7). Both are terminal and tear down the subscription.
//
// The hook keeps the live WebSocket subscription for the device for as long as
// the widget is mounted so terminal updates are never missed between commands.

function showToast(toastId, status, ctx) {
  const fb = feedbackForStatus(status, ctx);
  if (!fb) return;
  const opts = { id: toastId, description: fb.description };
  switch (fb.variant) {
    case TOAST_VARIANT.SUCCESS:
      toast.success(fb.message, opts);
      break;
    case TOAST_VARIANT.ERROR:
      toast.error(fb.message, opts);
      break;
    case TOAST_VARIANT.LOADING:
      toast.loading(fb.message, opts);
      break;
    default:
      toast(fb.message, opts);
  }
}

export function useDeviceCommand(deviceId, { deviceLabel } = {}) {
  // command_id -> { toastId, ctx } for commands awaiting a terminal status.
  const pending = useRef(new Map());

  // Maintain a single subscription to this device's channel while mounted so
  // command_status updates (Req 9.4, 9.7) are received for any in-flight command.
  useEffect(() => {
    if (!deviceId) return undefined;
    const channel = `device:${deviceId}`;
    const unsubscribe = realtimeClient.subscribe(channel, (msg) => {
      if (msg.type !== "command_status") return;
      const entry = pending.current.get(msg.command_id);
      if (!entry) return;
      showToast(entry.toastId, msg.status, entry.ctx);
      if (isTerminalStatus(msg.status)) {
        pending.current.delete(msg.command_id);
      }
    });
    return unsubscribe;
  }, [deviceId]);

  // Issue a command and start tracking it for ACK feedback.
  const sendCommand = useCallback(
    async ({ type, value } = {}) => {
      const ctx = { type, value, deviceLabel };
      const toastId = `cmd:${deviceId}:${type}:${value ?? ""}:${Date.now()}`;
      try {
        const result = await issueCommand(deviceId, { type, value });
        const status = result?.status || COMMAND_STATUS.SENT;
        // Show the initial (SENT/QUEUED) toast; track until terminal status.
        showToast(toastId, status, ctx);
        if (!isTerminalStatus(status)) {
          pending.current.set(result.command_id, { toastId, ctx });
        }
        return result;
      } catch (err) {
        const { message } = extractApiError(err);
        toast.error(message || "Failed to send command", { id: toastId });
        throw err;
      }
    },
    [deviceId, deviceLabel]
  );

  return { sendCommand };
}

export default useDeviceCommand;
