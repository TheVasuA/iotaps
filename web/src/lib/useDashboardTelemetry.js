import { useEffect, useMemo } from "react";
import { useAppDispatch } from "@/store/hooks";
import wsManager from "@/lib/websocket";
import { telemetryReceived } from "@/store/dashboardsSlice";

// Bridges the per-session WebSocket (design.md) into the dashboards slice for a
// set of devices referenced by the active dashboard's widgets (Req 7.4).
//
// Given the list of device ids the dashboard binds to, this hook:
//   1. opens the shared connection (idempotent),
//   2. subscribes to `device:{id}` channels for each bound device,
//   3. dispatches incoming `telemetry` frames into the store so widgets update,
//   4. unsubscribes on cleanup / when the device set changes.
//
// Non-telemetry frames (command_status / alert / notification) are ignored here
// and handled by their own features (tasks 9.x / 19.x).
export function useDashboardTelemetry(deviceIds) {
  const dispatch = useAppDispatch();

  // Stable, de-duplicated channel list so effect deps don't thrash on every
  // render when the caller passes a fresh array.
  const channels = useMemo(() => {
    const ids = Array.from(new Set((deviceIds || []).filter(Boolean)));
    return ids.map((id) => `device:${id}`);
  }, [deviceIds]);

  useEffect(() => {
    if (channels.length === 0) return undefined;

    wsManager.connect();
    wsManager.subscribe(channels);

    const off = wsManager.onMessage((msg) => {
      if (msg.type !== "telemetry") return;
      dispatch(
        telemetryReceived({
          deviceId: msg.device_id,
          ts: msg.ts,
          data: msg.data,
        })
      );
    });

    return () => {
      off();
      wsManager.unsubscribe(channels);
    };
  }, [dispatch, channels]);
}

export default useDashboardTelemetry;
