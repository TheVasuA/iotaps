const LOG_PREFIX = "iotaps.rule.debug.log.";
const PANEL_OPEN_KEY = "iotaps.rule.debug.panelOpen";
export const MAX_DEBUG_LOGS = 80;

export function debugLogStorageKey(ruleId) {
  return `${LOG_PREFIX}${ruleId}`;
}

export function loadDebugLogs(ruleId) {
  if (!ruleId) return [];
  try {
    const raw = localStorage.getItem(debugLogStorageKey(ruleId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, MAX_DEBUG_LOGS) : [];
  } catch {
    return [];
  }
}

export function saveDebugLogs(ruleId, logs) {
  if (!ruleId) return;
  try {
    localStorage.setItem(
      debugLogStorageKey(ruleId),
      JSON.stringify((logs || []).slice(0, MAX_DEBUG_LOGS))
    );
  } catch {
    /* quota / private mode */
  }
}

export function clearDebugLogs(ruleId) {
  if (!ruleId) return;
  try {
    localStorage.removeItem(debugLogStorageKey(ruleId));
  } catch {
    /* ignore */
  }
}

export function loadDebugPanelOpen() {
  try {
    return localStorage.getItem(PANEL_OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

export function saveDebugPanelOpen(open) {
  try {
    localStorage.setItem(PANEL_OPEN_KEY, open ? "1" : "0");
  } catch {
    /* ignore */
  }
}
