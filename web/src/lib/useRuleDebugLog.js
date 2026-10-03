import { useCallback, useEffect, useState } from "react";
import {
  loadDebugLogs,
  saveDebugLogs,
  clearDebugLogs,
  loadDebugPanelOpen,
  saveDebugPanelOpen,
  MAX_DEBUG_LOGS,
} from "@/lib/ruleDebugLog";

/** Persisted Node-RED-style debug log for a single rule editor session. */
export function useRuleDebugLog(ruleId) {
  const [logs, setLogs] = useState([]);
  const [open, setOpen] = useState(loadDebugPanelOpen);

  useEffect(() => {
    setLogs(ruleId ? loadDebugLogs(ruleId) : []);
  }, [ruleId]);

  const appendLog = useCallback(
    (entry) => {
      if (!ruleId) return;
      setLogs((prev) => {
        const next = [{ ...entry, ts: entry.ts ?? Date.now() }, ...prev].slice(0, MAX_DEBUG_LOGS);
        saveDebugLogs(ruleId, next);
        return next;
      });
    },
    [ruleId]
  );

  const clearLogs = useCallback(() => {
    if (!ruleId) return;
    clearDebugLogs(ruleId);
    setLogs([]);
  }, [ruleId]);

  const toggleOpen = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      saveDebugPanelOpen(next);
      return next;
    });
  }, []);

  return { logs, open, appendLog, clearLogs, toggleOpen };
}
