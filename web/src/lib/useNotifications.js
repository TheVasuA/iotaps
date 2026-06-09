import { useEffect } from "react";
import { toast } from "sonner";
import { useAppDispatch } from "@/store/hooks";
import wsManager from "@/lib/websocket";
import { notificationReceived } from "@/store/notificationsSlice";

// Bridges the per-session WebSocket into the notifications slice (Task 19.7,
// Req 20.2). The Notification_Sender delivers in-app notifications which are
// fanned out over the gateway as `{type:"notification", title, body}` frames
// (design "WebSocket message contract"). This hook:
//   1. opens the shared connection (idempotent),
//   2. dispatches incoming `notification` frames into the store so the
//      notification center + unread badge update,
//   3. raises a transient toast so the user sees it immediately.
//
// Mounted once at the app-shell level. Non-notification frames (telemetry /
// command_status / alert) are ignored here and handled by their own features.
export function useNotifications() {
  const dispatch = useAppDispatch();

  useEffect(() => {
    wsManager.connect();

    const off = wsManager.onMessage((msg) => {
      if (!msg || msg.type !== "notification") return;
      const title = msg.title || null;
      const body = msg.body || null;
      dispatch(notificationReceived({ title, body }));
      // Surface it transiently; the notification center keeps the history.
      toast(title || "Notification", body ? { description: body } : undefined);
    });

    return () => {
      off();
    };
  }, [dispatch]);
}

export default useNotifications;
