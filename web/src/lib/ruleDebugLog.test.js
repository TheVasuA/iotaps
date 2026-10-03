import { describe, it, expect, beforeEach } from "vitest";
import {
  loadDebugLogs,
  saveDebugLogs,
  clearDebugLogs,
  debugLogStorageKey,
  MAX_DEBUG_LOGS,
} from "./ruleDebugLog.js";

describe("ruleDebugLog storage", () => {
  const ruleId = "test-rule-id";
  let store;

  beforeEach(() => {
    store = {};
    globalThis.localStorage = {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => {
        store[k] = String(v);
      },
      removeItem: (k) => {
        delete store[k];
      },
      clear: () => {
        store = {};
      },
    };
  });

  it("round-trips log entries for a rule", () => {
    const entries = [{ ts: 1, level: "info", message: "Hello" }];
    saveDebugLogs(ruleId, entries);
    expect(loadDebugLogs(ruleId)).toEqual(entries);
    expect(localStorage.getItem(debugLogStorageKey(ruleId))).toBeTruthy();
  });

  it("caps stored logs at MAX_DEBUG_LOGS", () => {
    const many = Array.from({ length: MAX_DEBUG_LOGS + 5 }, (_, i) => ({
      ts: i,
      level: "info",
      message: String(i),
    }));
    saveDebugLogs(ruleId, many);
    expect(loadDebugLogs(ruleId)).toHaveLength(MAX_DEBUG_LOGS);
  });

  it("clear removes persisted logs", () => {
    saveDebugLogs(ruleId, [{ ts: 1, message: "x" }]);
    clearDebugLogs(ruleId);
    expect(loadDebugLogs(ruleId)).toEqual([]);
  });
});
