import { useEffect, useState, useCallback } from "react";
import wsManager from "@/lib/websocket";

const MAX_EVENTS = 100;

/**
 * Collects realtime device-channel frames for the Events tab (status, telemetry
 * snapshots, command_status, alert).
 */
export function useDeviceEventLog(deviceId) {
  const [events, setEvents] = useState([]);

  const push = useCallback((entry) => {
    setEvents((prev) => [{ ...entry, ts: entry.ts ?? Date.now() }, ...prev].slice(0, MAX_EVENTS));
  }, []);

  useEffect(() => {
    if (!deviceId) return undefined;
    const channel = `device:${deviceId}`;
    wsManager.connect();
    wsManager.subscribe([channel]);

    const off = wsManager.onMessage((msg) => {
      if (!msg || msg.device_id !== deviceId) return;
      if (msg.type === "telemetry") {
        push({
          level: "info",
          kind: "telemetry",
          message: `Telemetry: ${Object.keys(msg.data || {}).join(", ") || "update"}`,
        });
        return;
      }
      if (msg.type === "command_status") {
        push({
          level: msg.status === "CONFIRMED" ? "success" : msg.status === "UNACKNOWLEDGED" ? "error" : "info",
          kind: "command",
          message: `Command ${msg.command_id?.slice(0, 8) || ""} → ${msg.status}`,
        });
        return;
      }
      if (msg.type === "alert") {
        push({ level: "warn", kind: "alert", message: msg.message || msg.title || "Alert" });
        return;
      }
      if (msg.type === "status") {
        push({ level: "info", kind: "status", message: `Device ${msg.status}` });
      }
    });

    return () => {
      off?.();
      wsManager.unsubscribe([channel]);
    };
  }, [deviceId, push]);

  return events;
}
