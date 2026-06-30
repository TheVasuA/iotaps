import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Lightning,
  Plug,
  PlugsConnected,
  Terminal,
  UploadSimple,
  Warning,
  CircleNotch,
  Trash,
  Copy,
  DownloadSimple,
  Cpu,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  EspWebFlasher,
  SerialLineBuffer,
  FLASH_PHASE,
  MONITOR_BAUD_RATES,
  FLASH_BAUD_RATE,
  DEFAULT_FLASH_ADDRESS,
  isWebSerialSupported,
  readFirmwareFile,
  parseFlashAddress,
  classifyFlashError,
} from "@/lib/webFlasher";
import { listDevices } from "@/lib/devicesApi";
import {
  buildBlinkSketch,
  DEFAULT_MQTT_HOST,
  DEFAULT_MQTT_PORT,
} from "@/lib/sampleFirmware";

// Web Flasher + serial monitor (Task 11.2, Req 12.1-12.3).
//
// Flashes ESP32/ESP8266 firmware from the browser over Web Serial using
// esptool-js (Req 12.1), streams the device's serial output into a live monitor
// (Req 12.2), and surfaces a clear failure when the serial link drops during
// flashing or monitoring (Req 12.3). Browsers without Web Serial get a guarded,
// read-only explanation instead of a broken control surface.

const HEX_ADDRESS_DEFAULT = `0x${DEFAULT_FLASH_ADDRESS.toString(16)}`;

export default function WebFlasherPage() {
  const supported = useMemo(() => isWebSerialSupported(), []);

  const [phase, setPhase] = useState(FLASH_PHASE.IDLE);
  const [chipName, setChipName] = useState(null);
  const [firmware, setFirmware] = useState(null); // { name, size, data }
  const [address, setAddress] = useState(HEX_ADDRESS_DEFAULT);
  const [progress, setProgress] = useState(0);
  const [monitorBaud, setMonitorBaud] = useState(FLASH_BAUD_RATE);
  const [monitorLines, setMonitorLines] = useState([]);
  const [logLines, setLogLines] = useState([]);
  const [error, setError] = useState(null);

  const flasherRef = useRef(null);
  const lineBufferRef = useRef(new SerialLineBuffer());
  const monitorEndRef = useRef(null);

  // --- Sample firmware code (Blink LED with the device's generated token) ---
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [ssid, setSsid] = useState("");
  const [wifiPassword, setWifiPassword] = useState("");
  const [brokerHost, setBrokerHost] = useState(DEFAULT_MQTT_HOST);

  // Load the caller's devices so we can offer their generated tokens.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const list = await listDevices();
        if (!active) return;
        setDevices(list);
        if (list.length > 0) setSelectedDeviceId(list[0].id);
      } catch {
        // Non-fatal: the sample-code section just falls back to a placeholder
        // token. The flasher itself doesn't need the device list.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const selectedDevice = useMemo(
    () => devices.find((d) => d.id === selectedDeviceId) || null,
    [devices, selectedDeviceId]
  );

  const sampleCode = useMemo(
    () =>
      buildBlinkSketch({
        token: selectedDevice?.device_token,
        label: selectedDevice?.label,
        host: brokerHost.trim() || DEFAULT_MQTT_HOST,
        port: DEFAULT_MQTT_PORT,
        ssid: ssid.trim() || undefined,
        password: wifiPassword.trim() || undefined,
      }),
    [selectedDevice, brokerHost, ssid, wifiPassword]
  );

  const onCopyCode = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(sampleCode);
      toast.success("Sample code copied to clipboard");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }, [sampleCode]);

  const onDownloadCode = useCallback(() => {
    const safe = (selectedDevice?.label || "iotaps_device")
      .replace(/[^a-z0-9_-]+/gi, "_")
      .toLowerCase();
    const blob = new Blob([sampleCode], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safe}_blink.ino`;
    a.click();
    URL.revokeObjectURL(url);
  }, [sampleCode, selectedDevice]);

  const connected =
    phase === FLASH_PHASE.CONNECTED ||
    phase === FLASH_PHASE.FLASHING ||
    phase === FLASH_PHASE.DONE ||
    phase === FLASH_PHASE.MONITORING ||
    phase === FLASH_PHASE.ERROR;

  const busy =
    phase === FLASH_PHASE.CONNECTING || phase === FLASH_PHASE.FLASHING;

  const appendLog = useCallback((line) => {
    setLogLines((prev) => {
      const next = [...prev, line];
      return next.length > 500 ? next.slice(next.length - 500) : next;
    });
  }, []);

  // Auto-scroll the monitor to the latest line.
  useEffect(() => {
    monitorEndRef.current?.scrollIntoView({ block: "end" });
  }, [monitorLines]);

  // Release the serial port if the user navigates away mid-session.
  useEffect(() => {
    return () => {
      flasherRef.current?.disconnect();
    };
  }, []);

  const handleConnectionLost = useCallback(
    (info) => {
      // Req 12.3: report the lost connection prominently.
      setError(info.message);
      setPhase(FLASH_PHASE.ERROR);
      toast.error("Serial connection lost", { description: info.message });
    },
    []
  );

  const getFlasher = useCallback(() => {
    if (!flasherRef.current) {
      flasherRef.current = new EspWebFlasher({
        onLog: (line) => appendLog(line),
        onProgress: (written, total) =>
          setProgress(total > 0 ? Math.round((written / total) * 100) : 0),
        onChip: (name) => setChipName(name),
        onSerialData: (chunk) => {
          const newLines = lineBufferRef.current.push(chunk);
          if (newLines.length) {
            setMonitorLines([...lineBufferRef.current.lines]);
          }
        },
        onConnectionLost: handleConnectionLost,
      });
    }
    return flasherRef.current;
  }, [appendLog, handleConnectionLost]);

  const onConnect = useCallback(async () => {
    setError(null);
    setPhase(FLASH_PHASE.CONNECTING);
    try {
      const flasher = getFlasher();
      const chip = await flasher.connect();
      setPhase(FLASH_PHASE.CONNECTED);
      toast.success(`Connected to ${chip}`);
    } catch (err) {
      const info = classifyFlashError(err);
      setError(info.message);
      setPhase(FLASH_PHASE.IDLE);
      // requestPort() rejects when the user cancels the picker; keep that quiet.
      if (!/no port selected|cancel/i.test(info.message)) {
        toast.error("Could not connect", { description: info.message });
      }
      // Drop the half-initialised flasher so the next attempt starts clean.
      await flasherRef.current?.disconnect();
      flasherRef.current = null;
    }
  }, [getFlasher]);

  const onSelectFirmware = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const data = await readFirmwareFile(file);
      setFirmware({ name: file.name, size: data.length, data });
    } catch (err) {
      toast.error("Could not read firmware file", {
        description: classifyFlashError(err).message,
      });
    }
  }, []);

  const onFlash = useCallback(async () => {
    const parsedAddress = parseFlashAddress(address);
    if (parsedAddress === null) {
      toast.error("Invalid flash address", {
        description: "Enter a hex (0x10000) or decimal offset.",
      });
      return;
    }
    if (!firmware) {
      toast.error("Select a firmware file first");
      return;
    }
    setError(null);
    setProgress(0);
    setPhase(FLASH_PHASE.FLASHING);
    try {
      await getFlasher().flash(firmware.data, parsedAddress);
      setProgress(100);
      setPhase(FLASH_PHASE.DONE);
      toast.success("Firmware flashed", {
        description: `${firmware.name} written to ${chipName ?? "device"}.`,
      });
    } catch (err) {
      const info = classifyFlashError(err);
      setError(info.message);
      setPhase(FLASH_PHASE.ERROR);
      if (!info.connectionLost) {
        // Connection-loss already toasted via onConnectionLost.
        toast.error("Flashing failed", { description: info.message });
      }
    }
  }, [address, firmware, getFlasher, chipName]);

  const onStartMonitor = useCallback(async () => {
    setError(null);
    lineBufferRef.current.clear();
    setMonitorLines([]);
    setPhase(FLASH_PHASE.MONITORING);
    try {
      // startMonitor resolves only when the read loop stops.
      await getFlasher().startMonitor(monitorBaud);
    } catch (err) {
      const info = classifyFlashError(err);
      setError(info.message);
      setPhase(FLASH_PHASE.ERROR);
      toast.error("Serial monitor stopped", { description: info.message });
    }
  }, [getFlasher, monitorBaud]);

  const onStopMonitor = useCallback(() => {
    flasherRef.current?.stopMonitor();
    setPhase(FLASH_PHASE.CONNECTED);
  }, []);

  const onDisconnect = useCallback(async () => {
    await flasherRef.current?.disconnect();
    flasherRef.current = null;
    lineBufferRef.current.clear();
    setPhase(FLASH_PHASE.IDLE);
    setChipName(null);
    setProgress(0);
    setMonitorLines([]);
    setError(null);
  }, []);

  // --- Unsupported-browser guard (Req: degrade gracefully) -----------------
  if (!supported) {
    return (
      <section className="mx-auto max-w-3xl space-y-6">
        <header>
          <h1 className="text-2xl font-semibold text-primary">Web Flasher</h1>
          <p className="text-sm text-muted-foreground">
            Flash firmware and watch serial output from your browser.
          </p>
        </header>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <Warning size={22} className="text-amber-500" />
              Web Serial not available
            </CardTitle>
            <CardDescription>
              This browser does not support the Web Serial API.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>
              The Web Flasher needs the Web Serial API, which is available in
              Chromium-based browsers (Chrome, Edge, Opera) served over HTTPS or
              localhost.
            </p>
            <p>
              Open this page in a supported browser to flash your ESP32 or
              ESP8266 device.
            </p>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-primary">Web Flasher</h1>
          <p className="text-sm text-muted-foreground">
            Flash ESP32 / ESP8266 firmware and monitor serial output from your
            browser.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {chipName ? <Badge variant="success">{chipName}</Badge> : null}
          {connected ? (
            <Button variant="outline" onClick={onDisconnect} disabled={busy}>
              <PlugsConnected size={16} />
              Disconnect
            </Button>
          ) : (
            <Button onClick={onConnect} disabled={busy}>
              {phase === FLASH_PHASE.CONNECTING ? (
                <CircleNotch size={16} className="animate-spin" />
              ) : (
                <Plug size={16} />
              )}
              Connect device
            </Button>
          )}
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          <Warning size={18} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {/* Sample firmware: Blink LED with the device's generated token */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <Cpu size={20} className="text-primary" />
            Sample firmware (Blink LED)
          </CardTitle>
          <CardDescription>
            Pick one of your devices to generate a ready-to-compile Arduino
            sketch with its unique token baked in. Compile it in the Arduino IDE,
            export the .bin, then flash it below.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sample-device">Device</Label>
              {devices.length > 0 ? (
                <select
                  id="sample-device"
                  value={selectedDeviceId}
                  onChange={(e) => setSelectedDeviceId(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  {devices.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label || d.device_uid || d.id}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No devices yet — provision one from the Devices page to get a
                  token. The sample below uses a placeholder until then.
                </p>
              )}
              {selectedDevice ? (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  Token:
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                    {selectedDevice.device_token || "no active credential"}
                  </code>
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="broker-host">MQTT broker host</Label>
              <Input
                id="broker-host"
                value={brokerHost}
                onChange={(e) => setBrokerHost(e.target.value)}
                placeholder={DEFAULT_MQTT_HOST}
              />
              <p className="text-xs text-muted-foreground">
                Port {DEFAULT_MQTT_PORT} (MQTT). Override the host only if you
                run a private broker.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wifi-ssid">Wi-Fi SSID</Label>
              <Input
                id="wifi-ssid"
                value={ssid}
                onChange={(e) => setSsid(e.target.value)}
                placeholder="YOUR_WIFI_SSID"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wifi-pass">Wi-Fi password</Label>
              <Input
                id="wifi-pass"
                value={wifiPassword}
                onChange={(e) => setWifiPassword(e.target.value)}
                placeholder="YOUR_WIFI_PASSWORD"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={onCopyCode}>
              <Copy size={16} />
              Copy code
            </Button>
            <Button variant="outline" size="sm" onClick={onDownloadCode}>
              <DownloadSimple size={16} />
              Download .ino
            </Button>
          </div>

          <pre className="max-h-80 overflow-auto rounded-lg border border-border bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-100">
            <code>{sampleCode}</code>
          </pre>
        </CardContent>
      </Card>

      {/* Flashing card (Req 12.1) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <Lightning size={20} className="text-primary" />
            Flash firmware
          </CardTitle>
          <CardDescription>
            Select a compiled firmware binary (.bin) and write it to the
            connected device.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="firmware">Firmware file</Label>
              <Input
                id="firmware"
                type="file"
                accept=".bin,application/octet-stream"
                onChange={onSelectFirmware}
                disabled={busy}
              />
              {firmware ? (
                <p className="text-xs text-muted-foreground">
                  {firmware.name} ({firmware.size.toLocaleString()} bytes)
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="address">Flash address</Label>
              <Input
                id="address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="0x0"
                disabled={busy}
              />
              <p className="text-xs text-muted-foreground">
                Use 0x0 for a merged image, 0x10000 for a bare app image.
              </p>
            </div>
          </div>

          {phase === FLASH_PHASE.FLASHING ||
          phase === FLASH_PHASE.DONE ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {phase === FLASH_PHASE.DONE ? "Complete" : "Writing…"}
                </span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${progress}%` }}
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            </div>
          ) : null}

          <Button
            onClick={onFlash}
            disabled={!connected || busy || !firmware}
          >
            {phase === FLASH_PHASE.FLASHING ? (
              <CircleNotch size={16} className="animate-spin" />
            ) : (
              <UploadSimple size={16} />
            )}
            Flash device
          </Button>
        </CardContent>
      </Card>

      {/* Serial monitor card (Req 12.2) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <Terminal size={20} className="text-primary" />
            Serial monitor
          </CardTitle>
          <CardDescription>
            Watch the device's serial output in real time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="baud">Baud rate</Label>
              <select
                id="baud"
                value={monitorBaud}
                onChange={(e) => setMonitorBaud(Number(e.target.value))}
                disabled={phase === FLASH_PHASE.MONITORING}
                className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50"
              >
                {MONITOR_BAUD_RATES.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
            {phase === FLASH_PHASE.MONITORING ? (
              <Button variant="outline" onClick={onStopMonitor}>
                Stop monitor
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={onStartMonitor}
                disabled={!connected || busy}
              >
                <Terminal size={16} />
                Start monitor
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              aria-label="Clear monitor"
              onClick={() => {
                lineBufferRef.current.clear();
                setMonitorLines([]);
              }}
            >
              <Trash size={16} />
            </Button>
          </div>

          <div className="h-72 overflow-auto rounded-lg border border-border bg-zinc-950 p-3 font-mono text-xs text-emerald-300">
            {monitorLines.length === 0 ? (
              <p className="text-zinc-500">
                {phase === FLASH_PHASE.MONITORING
                  ? "Listening for serial output…"
                  : "Start the monitor to view serial output."}
              </p>
            ) : (
              monitorLines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))
            )}
            <div ref={monitorEndRef} />
          </div>
        </CardContent>
      </Card>

      {logLines.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Flasher log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-40 overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs text-muted-foreground">
              {logLines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}
