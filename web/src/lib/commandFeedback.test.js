// Unit + property tests for the command ACK feedback mapping (Task 9.3,
// Req 9.1, 9.2, 9.4). The mapping is pure, so it is exercised directly.

import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  COMMAND_STATUS,
  TOAST_VARIANT,
  feedbackForStatus,
  isTerminalStatus,
  describeCommand,
} from "./commandFeedback.js";

describe("describeCommand", () => {
  it("labels on/off/value commands", () => {
    expect(describeCommand({ type: "on" })).toBe("Turn on");
    expect(describeCommand({ type: "off" })).toBe("Turn off");
    expect(describeCommand({ type: "value", value: 128 })).toBe("Set to 128");
  });

  it("falls back to a generic label for unknown types", () => {
    expect(describeCommand({ type: "wat" })).toBe("Command");
    expect(describeCommand()).toBe("Command");
  });
});

describe("isTerminalStatus", () => {
  it("treats CONFIRMED and UNACKNOWLEDGED as terminal (Req 9.4, 9.7)", () => {
    expect(isTerminalStatus(COMMAND_STATUS.CONFIRMED)).toBe(true);
    expect(isTerminalStatus(COMMAND_STATUS.UNACKNOWLEDGED)).toBe(true);
  });

  it("treats SENT and QUEUED as non-terminal (still pending)", () => {
    expect(isTerminalStatus(COMMAND_STATUS.SENT)).toBe(false);
    expect(isTerminalStatus(COMMAND_STATUS.QUEUED)).toBe(false);
  });
});

describe("feedbackForStatus", () => {
  it("maps SENT to a pending/loading toast", () => {
    const fb = feedbackForStatus(COMMAND_STATUS.SENT, { type: "on" });
    expect(fb.variant).toBe(TOAST_VARIANT.LOADING);
    expect(fb.message).toContain("sent");
  });

  it("maps QUEUED to a pending/loading toast mentioning offline", () => {
    const fb = feedbackForStatus(COMMAND_STATUS.QUEUED, { type: "off" });
    expect(fb.variant).toBe(TOAST_VARIANT.LOADING);
    expect(fb.message).toContain("queued");
  });

  it("maps CONFIRMED to a success toast (Req 9.4)", () => {
    const fb = feedbackForStatus(COMMAND_STATUS.CONFIRMED, { type: "on" });
    expect(fb.variant).toBe(TOAST_VARIANT.SUCCESS);
    expect(fb.message).toContain("confirmed");
  });

  it("maps UNACKNOWLEDGED to an error toast (Req 9.7)", () => {
    const fb = feedbackForStatus(COMMAND_STATUS.UNACKNOWLEDGED, { type: "on" });
    expect(fb.variant).toBe(TOAST_VARIANT.ERROR);
    expect(fb.message).toContain("unacknowledged");
  });

  it("includes the device label in the message when provided", () => {
    const fb = feedbackForStatus(COMMAND_STATUS.CONFIRMED, {
      type: "value",
      value: 50,
      deviceLabel: "Pump A",
    });
    expect(fb.message).toContain("Pump A");
    expect(fb.message).toContain("Set to 50");
  });

  it("returns null for an unrecognised status", () => {
    expect(feedbackForStatus("BOGUS", { type: "on" })).toBeNull();
  });
});

describe("feedbackForStatus invariants over all valid statuses", () => {
  it("always yields a non-empty message and a known variant, with success only on CONFIRMED and error only on UNACKNOWLEDGED", () => {
    const statuses = Object.values(COMMAND_STATUS);
    const knownVariants = new Set(Object.values(TOAST_VARIANT));
    fc.assert(
      fc.property(
        fc.constantFrom(...statuses),
        fc.constantFrom("on", "off", "value"),
        fc.integer({ min: 0, max: 255 }),
        fc.option(fc.string(), { nil: undefined }),
        (status, type, value, deviceLabel) => {
          const fb = feedbackForStatus(status, { type, value, deviceLabel });
          expect(fb).not.toBeNull();
          expect(knownVariants.has(fb.variant)).toBe(true);
          expect(typeof fb.message).toBe("string");
          expect(fb.message.length).toBeGreaterThan(0);

          // Success is reserved for CONFIRMED (Req 9.4); error for
          // UNACKNOWLEDGED (Req 9.7); SENT/QUEUED stay pending (loading).
          if (fb.variant === TOAST_VARIANT.SUCCESS) {
            expect(status).toBe(COMMAND_STATUS.CONFIRMED);
          }
          if (fb.variant === TOAST_VARIANT.ERROR) {
            expect(status).toBe(COMMAND_STATUS.UNACKNOWLEDGED);
          }
          if (
            status === COMMAND_STATUS.SENT ||
            status === COMMAND_STATUS.QUEUED
          ) {
            expect(fb.variant).toBe(TOAST_VARIANT.LOADING);
            expect(isTerminalStatus(status)).toBe(false);
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});
