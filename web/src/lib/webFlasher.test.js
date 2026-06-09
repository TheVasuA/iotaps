// Unit + property tests for the Web Flasher / serial-monitor logic
// (Task 11.2, Req 12.1-12.3). The pure helpers are exercised directly; the
// EspWebFlasher controller is tested with injected fakes so no hardware or
// real Web Serial API is required.

import { describe, it, expect, vi } from "vitest";
import fc from "fast-check";

import {
  isWebSerialSupported,
  splitSerialText,
  appendMonitorLines,
  SerialLineBuffer,
  parseFlashAddress,
  classifyFlashError,
  readFirmwareFile,
  EspWebFlasher,
  FLASH_PHASE,
  MONITOR_BAUD_RATES,
  DEFAULT_MAX_MONITOR_LINES,
} from "./webFlasher.js";

describe("isWebSerialSupported", () => {
  it("is true when navigator exposes serial", () => {
    expect(isWebSerialSupported({ serial: {} })).toBe(true);
  });
  it("is false without a serial property", () => {
    expect(isWebSerialSupported({})).toBe(false);
    expect(isWebSerialSupported(null)).toBe(false);
    expect(isWebSerialSupported(undefined)).toBe(false);
  });
  it("is false when serial is falsy", () => {
    expect(isWebSerialSupported({ serial: undefined })).toBe(false);
  });
});

describe("splitSerialText", () => {
  it("emits only completed lines and carries the remainder", () => {
    const r = splitSerialText("", "hello\nwor");
    expect(r.lines).toEqual(["hello"]);
    expect(r.pending).toBe("wor");
  });
  it("prepends the previous pending text", () => {
    const r = splitSerialText("wor", "ld\nbye\n");
    expect(r.lines).toEqual(["world", "bye"]);
    expect(r.pending).toBe("");
  });
  it("normalises \\r\\n and bare \\r to \\n", () => {
    const r = splitSerialText("", "a\r\nb\rc\n");
    expect(r.lines).toEqual(["a", "b", "c"]);
    expect(r.pending).toBe("");
  });
  it("handles empty input", () => {
    expect(splitSerialText("", "")).toEqual({ lines: [], pending: "" });
  });
});

describe("appendMonitorLines", () => {
  it("appends without mutating the input", () => {
    const orig = ["a"];
    const next = appendMonitorLines(orig, ["b", "c"], 10);
    expect(orig).toEqual(["a"]);
    expect(next).toEqual(["a", "b", "c"]);
  });
  it("bounds to the most recent maxLines", () => {
    const out = appendMonitorLines(["1", "2", "3"], ["4", "5"], 3);
    expect(out).toEqual(["3", "4", "5"]);
  });
  it("treats non-positive maxLines as 1", () => {
    expect(appendMonitorLines([], ["a", "b"], 0)).toEqual(["b"]);
  });
});

describe("SerialLineBuffer", () => {
  it("accumulates bounded lines across string pushes", () => {
    const buf = new SerialLineBuffer(2);
    expect(buf.push("one\ntwo\nthr")).toEqual(["one", "two"]);
    expect(buf.lines).toEqual(["one", "two"]);
    expect(buf.push("ee\n")).toEqual(["three"]);
    // bounded to 2 most recent
    expect(buf.lines).toEqual(["two", "three"]);
    expect(buf.pending).toBe("");
  });
  it("decodes Uint8Array chunks", () => {
    const buf = new SerialLineBuffer();
    const bytes = new TextEncoder().encode("boot\nready\n");
    expect(buf.push(bytes)).toEqual(["boot", "ready"]);
  });
  it("clear() resets lines and pending", () => {
    const buf = new SerialLineBuffer();
    buf.push("partial");
    buf.clear();
    expect(buf.lines).toEqual([]);
    expect(buf.pending).toBe("");
  });
});

describe("parseFlashAddress", () => {
  it("parses hex with 0x prefix", () => {
    expect(parseFlashAddress("0x10000")).toBe(65536);
    expect(parseFlashAddress("0X1000")).toBe(4096);
  });
  it("parses decimal", () => {
    expect(parseFlashAddress("4096")).toBe(4096);
    expect(parseFlashAddress("0")).toBe(0);
  });
  it("accepts non-negative integer numbers", () => {
    expect(parseFlashAddress(0)).toBe(0);
    expect(parseFlashAddress(65536)).toBe(65536);
  });
  it("rejects invalid input", () => {
    expect(parseFlashAddress("")).toBeNull();
    expect(parseFlashAddress("xyz")).toBeNull();
    expect(parseFlashAddress("-5")).toBeNull();
    expect(parseFlashAddress(-1)).toBeNull();
    expect(parseFlashAddress(1.5)).toBeNull();
    expect(parseFlashAddress(null)).toBeNull();
    expect(parseFlashAddress("0xZZ")).toBeNull();
  });
});

describe("classifyFlashError (Req 12.3)", () => {
  it("flags device-lost errors as connection loss", () => {
    const r = classifyFlashError(new Error("The device has been lost."));
    expect(r.connectionLost).toBe(true);
    expect(r.message).toMatch(/Serial connection lost/);
  });
  it("flags NetworkError DOMException-like objects", () => {
    const r = classifyFlashError({ name: "NetworkError", message: "boom" });
    expect(r.connectionLost).toBe(true);
  });
  it("treats protocol errors as non-connection failures", () => {
    const r = classifyFlashError(new Error("Invalid head of packet"));
    expect(r.connectionLost).toBe(false);
    expect(r.message).toBe("Invalid head of packet");
  });
  it("handles string and missing errors", () => {
    expect(classifyFlashError("disconnected").connectionLost).toBe(true);
    expect(classifyFlashError(undefined).message).toBe("Unknown error");
  });
});

describe("readFirmwareFile", () => {
  it("reads a blob into a Uint8Array", async () => {
    const blob = {
      arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    };
    const out = await readFirmwareFile(blob);
    expect(out).toBeInstanceOf(Uint8Array);
    expect(Array.from(out)).toEqual([1, 2, 3]);
  });
  it("rejects when no file is given", async () => {
    await expect(readFirmwareFile(null)).rejects.toThrow();
  });
});

describe("monitor baud rates", () => {
  it("includes the common 115200 default", () => {
    expect(MONITOR_BAUD_RATES).toContain(115200);
  });
});

// --- EspWebFlasher controller -------------------------------------------------

function makeFakeLoader({ flashImpl } = {}) {
  return vi.fn().mockImplementation((opts) => ({
    transport: opts.transport,
    chip: { CHIP_NAME: "ESP32" },
    main: vi.fn().mockResolvedValue("ESP32"),
    writeFlash: flashImpl ?? vi.fn().mockResolvedValue(undefined),
    after: vi.fn().mockResolvedValue(undefined),
  }));
}

function makeFakeTransport({ rawReadImpl } = {}) {
  return vi.fn().mockImplementation((device) => ({
    device,
    setDeviceLostCallback: vi.fn(),
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn().mockResolvedValue(undefined),
    rawRead:
      rawReadImpl ??
      vi.fn().mockImplementation(async (onData, isClosed) => {
        onData(new TextEncoder().encode("hello\n"));
        // stop immediately
        while (!isClosed()) break;
      }),
  }));
}

function makeFakeSerial() {
  return { requestPort: vi.fn().mockResolvedValue({ id: "port" }) };
}

describe("EspWebFlasher.connect (Req 12.1)", () => {
  it("requests a port, detects the chip, and reports it", async () => {
    const onChip = vi.fn();
    const flasher = new EspWebFlasher(
      { onChip },
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader(),
        TransportImpl: makeFakeTransport(),
      }
    );
    const chip = await flasher.connect();
    expect(chip).toBe("ESP32");
    expect(onChip).toHaveBeenCalledWith("ESP32");
    expect(flasher.isConnected).toBe(true);
  });

  it("throws when Web Serial is unavailable", async () => {
    const flasher = new EspWebFlasher({}, { serial: undefined });
    await expect(flasher.connect()).rejects.toThrow(/not supported/i);
  });
});

describe("EspWebFlasher.flash (Req 12.1, 12.3)", () => {
  it("writes the firmware and reports progress", async () => {
    const onProgress = vi.fn();
    const writeFlash = vi.fn().mockImplementation(async (opts) => {
      opts.reportProgress(0, 50, 100);
      opts.reportProgress(1, 100, 100);
    });
    const flasher = new EspWebFlasher(
      { onProgress },
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader({ flashImpl: writeFlash }),
        TransportImpl: makeFakeTransport(),
      }
    );
    await flasher.connect();
    await flasher.flash(new Uint8Array([1, 2, 3, 4]), 0x10000);
    expect(writeFlash).toHaveBeenCalledOnce();
    const opts = writeFlash.mock.calls[0][0];
    expect(opts.fileArray[0].address).toBe(0x10000);
    expect(opts.fileArray[0].data).toBeInstanceOf(Uint8Array);
    expect(onProgress).toHaveBeenCalledWith(100, 100);
  });

  it("reports a lost connection during flashing (Req 12.3)", async () => {
    const onConnectionLost = vi.fn();
    const writeFlash = vi
      .fn()
      .mockRejectedValue(new Error("The device has been lost."));
    const flasher = new EspWebFlasher(
      { onConnectionLost },
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader({ flashImpl: writeFlash }),
        TransportImpl: makeFakeTransport(),
      }
    );
    await flasher.connect();
    await expect(flasher.flash(new Uint8Array([1, 2]))).rejects.toThrow();
    expect(onConnectionLost).toHaveBeenCalledOnce();
    expect(onConnectionLost.mock.calls[0][0].connectionLost).toBe(true);
  });

  it("rejects an empty firmware image", async () => {
    const flasher = new EspWebFlasher(
      {},
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader(),
        TransportImpl: makeFakeTransport(),
      }
    );
    await flasher.connect();
    await expect(flasher.flash(new Uint8Array([]))).rejects.toThrow(/empty/i);
  });
});

describe("EspWebFlasher.startMonitor (Req 12.2, 12.3)", () => {
  it("streams serial data chunks to onSerialData", async () => {
    const chunks = [];
    const flasher = new EspWebFlasher(
      { onSerialData: (c) => chunks.push(c) },
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader(),
        TransportImpl: makeFakeTransport(),
      }
    );
    await flasher.connect();
    await flasher.startMonitor(115200);
    expect(chunks.length).toBeGreaterThan(0);
  });

  it("reports a lost connection while monitoring (Req 12.3)", async () => {
    const onConnectionLost = vi.fn();
    const rawRead = vi
      .fn()
      .mockRejectedValue(new Error("The device has been lost."));
    const flasher = new EspWebFlasher(
      { onConnectionLost },
      {
        serial: makeFakeSerial(),
        ESPLoaderImpl: makeFakeLoader(),
        TransportImpl: makeFakeTransport({ rawReadImpl: rawRead }),
      }
    );
    await flasher.connect();
    await expect(flasher.startMonitor()).rejects.toThrow(
      /Serial connection lost/
    );
    expect(onConnectionLost).toHaveBeenCalledOnce();
  });
});

// --- Property test -----------------------------------------------------------

describe("serial line buffering invariants (Req 12.2)", () => {
  it("Property: chunking is invisible — any split yields the same lines and bounded buffer", () => {
    // Feature: iotaps-platform, Property: serial monitor line assembly is
    // independent of how the byte stream is chunked.
    fc.assert(
      fc.property(
        // A body of text built from line-ish tokens, plus a list of split
        // points that re-chunk it arbitrarily.
        fc.array(
          fc.stringOf(
            fc.constantFrom("a", "b", "c", " ", "\n", "\r", "1", "2"),
            { maxLength: 12 }
          ),
          { maxLength: 40 }
        ),
        fc.array(fc.integer({ min: 1, max: 8 }), { maxLength: 40 }),
        (tokens, splitSizes) => {
          const text = tokens.join("");

          // Reference: feed the whole text at once.
          const whole = new SerialLineBuffer(DEFAULT_MAX_MONITOR_LINES);
          whole.push(text);
          const wholeLines = [...whole.lines];
          const wholePending = whole.pending;

          // Re-chunk the text into pieces of the given sizes (cycled).
          const chunked = new SerialLineBuffer(DEFAULT_MAX_MONITOR_LINES);
          const sizes = splitSizes.length ? splitSizes : [1];
          let i = 0;
          let s = 0;
          const emitted = [];
          while (i < text.length) {
            const size = sizes[s % sizes.length];
            const piece = text.slice(i, i + size);
            emitted.push(...chunked.push(piece));
            i += size;
            s += 1;
          }

          // Completed lines and pending must match the whole-feed reference.
          expect(chunked.lines).toEqual(wholeLines);
          expect(chunked.pending).toBe(wholePending);
          // Lines returned incrementally equal the final buffered lines when
          // under the bound (no line is ever dropped for short inputs).
          if (wholeLines.length <= DEFAULT_MAX_MONITOR_LINES) {
            expect(emitted).toEqual(wholeLines);
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});

describe("FLASH_PHASE", () => {
  it("exposes the lifecycle phases used by the page", () => {
    expect(Object.values(FLASH_PHASE)).toEqual(
      expect.arrayContaining([
        "idle",
        "connecting",
        "connected",
        "flashing",
        "done",
        "error",
        "monitoring",
      ])
    );
  });
});
