import { useState } from "react";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import useDeviceCommand from "@/components/devices/useDeviceCommand";

// ToggleControl (Task 9.3, Req 9.1): an ON/OFF control wired to the command API.
// Toggling issues an `on`/`off` command for the device and surfaces Sonner ACK
// feedback (SENT/QUEUED -> CONFIRMED/UNACKNOWLEDGED) via useDeviceCommand.
//
// The switch reflects the user's intent optimistically and reverts if the API
// call to issue the command fails outright (a rejected request, e.g. queue
// failure on an offline device, Req 9.5). ACK timeouts (UNACKNOWLEDGED) are
// surfaced as a toast but do not revert the intended state, matching the
// "control even when offline" goal of Req 9.
export default function ToggleControl({
  deviceId,
  deviceLabel,
  label = "Power",
  defaultOn = false,
  disabled = false,
}) {
  const [on, setOn] = useState(defaultOn);
  const [busy, setBusy] = useState(false);
  const { sendCommand } = useDeviceCommand(deviceId, { deviceLabel });

  const onToggle = async (next) => {
    if (busy) return;
    setOn(next); // optimistic
    setBusy(true);
    try {
      await sendCommand({ type: next ? "on" : "off" });
    } catch {
      setOn(!next); // revert on hard failure (request rejected)
    } finally {
      setBusy(false);
    }
  };

  const controlId = `toggle-${deviceId}`;
  return (
    <div className="flex items-center justify-between gap-4">
      <Label htmlFor={controlId}>{label}</Label>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground" aria-hidden="true">
          {on ? "On" : "Off"}
        </span>
        <Switch
          id={controlId}
          checked={on}
          onChange={onToggle}
          disabled={disabled || busy}
        />
      </div>
    </div>
  );
}
