// Web Flasher / serial monitor logic (Task 11.2, Req 12.1-12.3).
//
// This module owns the browser-side firmware flashing and serial-monitoring
// logic that the WebFlasherPage drives. It is split into two layers:
//
//   1. Pure helpers (Web Serial support detection, serial-text line buffering,
//      firmware file reading, flash-error classification). These are framework
//      free so they can be unit- and property-tested without hardware.
//   2. A thin `EspWebFlasher` controller that wraps esptool-js (ESPLoader +
//      Transport) over the Web Serial API. It performs the actual connect /
//      flash / monitor work against a real device and surfaces connection-loss
//      failures (Req 12.3) via callbacks.
//
// esptool-js handles ESP32 *and* ESP8266 because ESPLoader.main() detects the
// connected chip, so a single flash path serves both families (Req 12.1).

import { ESPLoader, Transport } from "esptool-js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Baud rate used to talk to the ROM/stub bootloader while flashing. 115200 is
// the universally safe default; higher rates can be requested by the loader
// once connected.
export const FLASH_BAUD_RATE = 115200;

// Baud rates offered for the serial monitor. ESP firmware most commonly logs at
// 115200, but 9600 and 74880 (ESP8266 boot ROM) are common enough to offer.
export const MONITOR_BAUD_RATES = Object.freeze([
  9600, 74880, 115200, 230400, 460800, 921600,
]);

// Default flash offset for a single firmware image. A combined application
// binary (bootloader + partition table + app merged) is written at 0x0; a bare
// application image is typically written at 0x10000. We default to 0x0 so a
// merged "factory" binary just works, and let the user override.
export const DEFAULT_FLASH_ADDRESS = 0x0;

// Cap on retained serial-monitor lines so a chatty device cannot grow the DOM /
// memory without bound.
export const DEFAULT_MAX_MONITOR_LINES = 2000;

// ---------------------------------------------------------------------------
// Web Serial support detection
// ---------------------------------------------------------------------------

/**
 * Whether the Web Serial API is available in the current environment.
 *
 * The flasher requires `navigator.serial` (Chromium-based browsers over HTTPS
 * or localhost). Firefox/Safari and insecure contexts do not expose it, so the
 * UI must degrade gracefully rather than throw.
 *
 * @param {Navigator|object} [nav] navigator-like object (defaults to the global)
 * @returns {boolean}
 */
export function isWebSerialSupported(nav) {
  const n =
    nav ?? (typeof navigator !== "undefined" ? navigator : undefined);
  return !!(n && typeof n === "object" && "serial" in n && n.serial);
}

// ---------------------------------------------------------------------------
// Serial text -> lines buffering (serial monitor, Req 12.2)
// ---------------------------------------------------------------------------

/**
 * Split a stream of serial text into completed lines plus a trailing partial.
 *
 * Serial chunks arrive without respecting line boundaries, so we keep the
 * not-yet-terminated remainder in `pending` and only emit a line once its
 * newline arrives. `\r\n` and `\r` are normalised to `\n`.
 *
 * Invariant (exercised by the property test): feeding text in any chunking
 * always yields the same completed lines and final pending as feeding it whole.
 *
 * @param {string} pending carry-over from the previous call
 * @param {string} chunk newly received text
 * @returns {{ lines: string[], pending: string }}
 */
export function splitSerialText(pending, chunk) {
  let combined = `${pending ?? ""}${chunk ?? ""}`;
  // Defer a trailing CR: it may be the first half of a CRLF that only completes
  // in the next chunk. Converting it now would emit a premature blank line, so
  // hold it in pending instead — this keeps line assembly independent of how
  // the byte stream happens to be chunked.
  let heldCr = "";
  if (combined.endsWith("\r")) {
    heldCr = "\r";
    combined = combined.slice(0, -1);
  }
  const normalized = combined.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const parts = normalized.split("\n");
  // The last element is the (possibly empty) unterminated remainder.
  const remainder = parts.pop();
  return { lines: parts, pending: `${remainder ?? ""}${heldCr}` };
}

/**
 * Append completed lines to a bounded ring buffer, dropping the oldest first.
 *
 * @param {string[]} lines existing buffer
 * @param {string[]} incoming new completed lines
 * @param {number} [maxLines]
 * @returns {string[]} a new array (input is not mutated)
 */
export function appendMonitorLines(
  lines,
  incoming,
  maxLines = DEFAULT_MAX_MONITOR_LINES
) {
  const max = Number.isFinite(maxLines) && maxLines > 0 ? Math.floor(maxLines) : 1;
  const next = [...(lines ?? []), ...(incoming ?? [])];
  if (next.length <= max) return next;
  return next.slice(next.length - max);
}

/**
 * Stateful helper that turns raw serial byte chunks into bounded lines for the
 * monitor view. Wraps {@link splitSerialText} + {@link appendMonitorLines} and
 * owns a TextDecoder so multi-byte sequences split across chunks decode
 * correctly (stream: true).
 */
export class SerialLineBuffer {
  constructor(maxLines = DEFAULT_MAX_MONITOR_LINES) {
    this._pending = "";
    this._lines = [];
    this._maxLines = maxLines;
    this._decoder =
      typeof TextDecoder !== "undefined" ? new TextDecoder() : null;
  }

  /** Current completed lines (bounded). */
  get lines() {
    return this._lines;
  }

  /** The unterminated trailing text not yet emitted as a line. */
  get pending() {
    return this._pending;
  }

  /**
   * Push a chunk (Uint8Array of bytes or already-decoded string) and return the
   * newly completed lines from this chunk.
   * @param {Uint8Array|string} chunk
   * @returns {string[]} newly completed lines
   */
  push(chunk) {
    let text;
    if (typeof chunk === "string") {
      text = chunk;
    } else if (this._decoder && chunk) {
      text = this._decoder.decode(chunk, { stream: true });
    } else {
      text = "";
    }
    const { lines, pending } = splitSerialText(this._pending, text);
    this._pending = pending;
    if (lines.length) {
      this._lines = appendMonitorLines(this._lines, lines, this._maxLines);
    }
    return lines;
  }

  /** Reset all buffered state (e.g. when reconnecting). */
  clear() {
    this._pending = "";
    this._lines = [];
  }
}

// ---------------------------------------------------------------------------
// Firmware file reading
// ---------------------------------------------------------------------------

/**
 * Read a firmware File/Blob into a Uint8Array suitable for ESPLoader.writeFlash.
 * @param {Blob} file
 * @returns {Promise<Uint8Array>}
 */
export function readFirmwareFile(file) {
  if (!file || typeof file.arrayBuffer !== "function") {
    return Promise.reject(new Error("No firmware file selected"));
  }
  return file.arrayBuffer().then((buf) => new Uint8Array(buf));
}

// ---------------------------------------------------------------------------
// Flash-address parsing
// ---------------------------------------------------------------------------

/**
 * Parse a user-entered flash address (hex like "0x10000" or decimal) into a
 * non-negative integer offset, or null when invalid.
 * @param {string|number} input
 * @returns {number|null}
 */
export function parseFlashAddress(input) {
  if (typeof input === "number") {
    return Number.isInteger(input) && input >= 0 ? input : null;
  }
  if (typeof input !== "string") return null;
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = /^0x[0-9a-f]+$/i.test(trimmed)
    ? parseInt(trimmed, 16)
    : /^[0-9]+$/.test(trimmed)
    ? parseInt(trimmed, 10)
    : NaN;
  return Number.isInteger(value) && value >= 0 ? value : null;
}

// ---------------------------------------------------------------------------
// Error classification (connection-loss reporting, Req 12.3)
// ---------------------------------------------------------------------------

// Substrings that indicate the serial link dropped mid-operation rather than a
// logical/protocol error. Matching is case-insensitive.
const CONNECTION_LOSS_SIGNATURES = [
  "device has been lost",
  "device lost",
  "the device has been closed",
  "device disconnected",
  "disconnected",
  "network error", // Chromium surfaces unplug as a DOMException NetworkError
  "the port is closed",
  "port is already closed",
  "readable stream",
  "writable stream",
  "failed to open serial port",
  "break condition",
  "the device has been reset",
];

/**
 * Classify an error thrown during flashing/monitoring.
 *
 * Distinguishes a lost serial connection (Req 12.3 - must be reported as such)
 * from other failures so the UI can show the right message.
 *
 * @param {unknown} err
 * @returns {{ connectionLost: boolean, message: string }}
 */
export function classifyFlashError(err) {
  const raw =
    (err && (err.message || err.name)) ||
    (typeof err === "string" ? err : "") ||
    "Unknown error";
  const lower = String(raw).toLowerCase();
  const isNetworkException =
    !!err &&
    typeof err === "object" &&
    err.name === "NetworkError";
  const connectionLost =
    isNetworkException ||
    CONNECTION_LOSS_SIGNATURES.some((sig) => lower.includes(sig));
  return {
    connectionLost,
    message: connectionLost
      ? `Serial connection lost: ${raw}`
      : String(raw),
  };
}

// ---------------------------------------------------------------------------
// Flash lifecycle phases (drives UI state)
// ---------------------------------------------------------------------------

export const FLASH_PHASE = Object.freeze({
  IDLE: "idle",
  CONNECTING: "connecting",
  CONNECTED: "connected",
  FLASHING: "flashing",
  DONE: "done",
  ERROR: "error",
  MONITORING: "monitoring",
});

// ---------------------------------------------------------------------------
// EspWebFlasher controller (esptool-js over Web Serial)
// ---------------------------------------------------------------------------

/**
 * @typedef {object} FlasherCallbacks
 * @property {(line: string) => void} [onLog] loader/terminal log line
 * @property {(written: number, total: number) => void} [onProgress] flash progress
 * @property {(chunk: Uint8Array) => void} [onSerialData] raw monitor bytes
 * @property {(info: { connectionLost: boolean, message: string }) => void} [onConnectionLost]
 * @property {(chipName: string) => void} [onChip] detected chip name
 */

/**
 * Controller that owns the Web Serial port + esptool-js Transport/ESPLoader for
 * one device session. Designed so the React page only deals with high-level
 * connect / flash / monitor / disconnect calls and callback events.
 *
 * The DOM/Web-Serial dependencies are injected (defaulting to the globals) so
 * the controller can be constructed in tests without a real navigator.
 */
export class EspWebFlasher {
  /**
   * @param {FlasherCallbacks} [callbacks]
   * @param {{ serial?: object, ESPLoaderImpl?: Function, TransportImpl?: Function }} [deps]
   */
  constructor(callbacks = {}, deps = {}) {
    this._cb = callbacks;
    this._serial =
      deps.serial ??
      (typeof navigator !== "undefined" ? navigator.serial : undefined);
    this._ESPLoader = deps.ESPLoaderImpl ?? ESPLoader;
    this._Transport = deps.TransportImpl ?? Transport;

    this._port = null;
    this._transport = null;
    this._loader = null;
    this._chipName = null;
    this._monitoring = false;
  }

  get chipName() {
    return this._chipName;
  }

  get isConnected() {
    return !!this._transport;
  }

  _log(str) {
    this._cb.onLog?.(str);
  }

  /** esptool-js terminal interface bridging loader output to onLog. */
  _terminal() {
    return {
      clean: () => {},
      writeLine: (data) => this._log(String(data)),
      write: (data) => this._log(String(data)),
    };
  }

  _reportConnectionLost(err) {
    const info = classifyFlashError(err);
    this._cb.onConnectionLost?.(info);
    return info;
  }

  /**
   * Prompt the user for a serial port and connect the esptool-js loader to it.
   * Detects the chip so both ESP32 and ESP8266 are supported (Req 12.1).
   * @returns {Promise<string>} detected chip name
   */
  async connect() {
    if (!this._serial) {
      throw new Error("Web Serial API is not supported in this browser");
    }
    this._port = await this._serial.requestPort();
    this._transport = new this._Transport(this._port, true);
    // Surface unexpected unplugs even when we are not mid-operation.
    this._transport.setDeviceLostCallback?.(() =>
      this._reportConnectionLost(new Error("The device has been lost"))
    );

    this._loader = new this._ESPLoader({
      transport: this._transport,
      baudrate: FLASH_BAUD_RATE,
      terminal: this._terminal(),
    });

    const chip = await this._loader.main();
    this._chipName = typeof chip === "string" ? chip : this._loader.chip?.CHIP_NAME ?? "ESP";
    this._cb.onChip?.(this._chipName);
    return this._chipName;
  }

  /**
   * Flash a single firmware image to the connected device (Req 12.1). Reports a
   * lost connection to the caller (Req 12.3) and rethrows so the UI can mark the
   * operation failed.
   *
   * @param {Uint8Array} data firmware bytes
   * @param {number} [address] flash offset
   * @returns {Promise<void>}
   */
  async flash(data, address = DEFAULT_FLASH_ADDRESS) {
    if (!this._loader) {
      throw new Error("Not connected to a device");
    }
    if (!data || data.length === 0) {
      throw new Error("Firmware image is empty");
    }
    // esptool-js writeFlash wants the image as a binary string in this build's
    // FlashOptions; pass bytes directly which the loader pads/handles.
    const fileArray = [{ data, address }];
    try {
      await this._loader.writeFlash({
        fileArray,
        flashSize: "keep",
        flashMode: "keep",
        flashFreq: "keep",
        eraseAll: false,
        compress: true,
        reportProgress: (_fileIndex, written, total) =>
          this._cb.onProgress?.(written, total),
      });
      // Reset out of the bootloader so the freshly flashed app runs.
      await this._loader.after?.("hard_reset");
    } catch (err) {
      const info = classifyFlashError(err);
      if (info.connectionLost) {
        this._cb.onConnectionLost?.(info);
      }
      throw err;
    }
  }

  /**
   * Stream serial output to the onSerialData callback until {@link stopMonitor}
   * is called or the device is lost (Req 12.2). Resolves when reading stops.
   * @param {number} [baud]
   * @returns {Promise<void>}
   */
  async startMonitor(baud = FLASH_BAUD_RATE) {
    if (!this._transport) {
      throw new Error("Not connected to a device");
    }
    // Reconnect the underlying port at the requested monitor baud rate.
    await this._transport.disconnect?.();
    await this._transport.connect?.(baud);
    this._monitoring = true;
    try {
      await this._transport.rawRead(
        (chunk) => this._cb.onSerialData?.(chunk),
        () => !this._monitoring
      );
    } catch (err) {
      const info = this._reportConnectionLost(err);
      throw new Error(info.message);
    }
  }

  /** Signal the monitor read loop to stop. */
  stopMonitor() {
    this._monitoring = false;
  }

  /** Disconnect and release the serial port. Safe to call repeatedly. */
  async disconnect() {
    this._monitoring = false;
    try {
      await this._transport?.disconnect?.();
    } catch {
      /* ignore close errors */
    }
    this._transport = null;
    this._loader = null;
    this._port = null;
    this._chipName = null;
  }
}

export default EspWebFlasher;
