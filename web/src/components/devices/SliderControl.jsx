import { useState } from "react";
import { Label } from "@/components/ui/label";
import useDeviceCommand from "@/components/devices/useDeviceCommand";

// SliderControl (Task 9.3, Req 9.2): a slider control wired to the command API.
// Releasing the slider issues a `value` command for the device and surfaces
// Sonner ACK feedback (SENT/QUEUED -> CONFIRMED/UNACKNOWLEDGED) via
// useDeviceCommand.
//
// The command is sent on commit (pointer/keyboard release via onChange of the
// range input fires continuously, so we send on `onMouseUp`/`onKeyUp`/`onTouchEnd`
// to avoid flooding the broker). The displayed value tracks the slider live.
export default function SliderControl({
  deviceId,
  deviceLabel,
  label = "Level",
  min = 0,
  max = 255,
  step = 1,
  defaultValue = 0,
  disabled = false,
}) {
  const [value, setValue] = useState(defaultValue);
  const [busy, setBusy] = useState(false);
  const { sendCommand } = useDeviceCommand(deviceId, { deviceLabel });

  const commit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await sendCommand({ type: "value", value });
    } catch {
      /* feedback handled by the toast; keep the slider where the user left it */
    } finally {
      setBusy(false);
    }
  };

  const controlId = `slider-${deviceId}`;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor={controlId}>{label}</Label>
        <span className="text-sm tabular-nums text-muted-foreground">
          {value}
        </span>
      </div>
      <input
        id={controlId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled || busy}
        onChange={(e) => setValue(Number(e.target.value))}
        onMouseUp={commit}
        onTouchEnd={commit}
        onKeyUp={commit}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        className="h-2 w-full cursor-pointer appearance-none rounded-full bg-input accent-primary disabled:cursor-not-allowed disabled:opacity-50"
      />
    </div>
  );
}
