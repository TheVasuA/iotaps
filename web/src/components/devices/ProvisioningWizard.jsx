import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle, Copy, WarningCircle } from "@phosphor-icons/react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  provisionDevice,
  fetchDevices,
  selectDeviceGroups,
} from "@/store/devicesSlice";
import QrDisplay from "./QrDisplay";

// Multi-step device provisioning wizard (Req 5.1, 5.2, 5.4, 5.5).
//   Step 1 "details"  -> collect label, optional device UID, optional group.
//   Step 2 "review"   -> confirm before creating.
//   Step 3 "done"     -> show generated MQTT credentials (secret shown ONCE)
//                        and the QR code encoding the device identity.
const STEPS = ["details", "review", "done"];

export default function ProvisioningWizard({ open, onClose }) {
  const dispatch = useAppDispatch();
  const groups = useAppSelector(selectDeviceGroups);

  const [step, setStep] = useState("details");
  const [label, setLabel] = useState("");
  const [deviceUid, setDeviceUid] = useState("");
  const [groupId, setGroupId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { device, mqtt_credentials, qr }

  const reset = () => {
    setStep("details");
    setLabel("");
    setDeviceUid("");
    setGroupId("");
    setSubmitting(false);
    setResult(null);
  };

  const handleClose = () => {
    reset();
    onClose?.();
    // Refresh device list to show the new MQTT credentials
    dispatch(fetchDevices({ groupId: undefined, status: undefined }));
  };

  const onCreate = async () => {
    setSubmitting(true);
    try {
      const payload = await dispatch(
        provisionDevice({
          label: label.trim() || null,
          deviceUid: deviceUid.trim() || null,
          groupId: groupId || null,
        })
      ).unwrap();
      setResult(payload);
      setStep("done");
      toast.success("Device provisioned");
    } catch (err) {
      toast.error(err?.message || "Failed to provision device");
    } finally {
      setSubmitting(false);
    }
  };

  const copySecret = async () => {
    const token = result?.mqtt_credentials?.device_token || result?.device?.device_token;
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      toast.success("Device token copied");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  };

  const stepIndex = STEPS.indexOf(step);

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title="Provision device"
      description="Create a device, generate its MQTT credentials, and get its QR code."
    >
      <DialogBody className="space-y-5">
        <ol className="flex items-center gap-2 text-xs">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span
                className={
                  "inline-flex h-6 w-6 items-center justify-center rounded-full border text-[11px] " +
                  (i <= stepIndex
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground")
                }
              >
                {i + 1}
              </span>
              <span
                className={
                  i === stepIndex
                    ? "font-medium capitalize text-foreground"
                    : "capitalize text-muted-foreground"
                }
              >
                {s}
              </span>
              {i < STEPS.length - 1 ? (
                <span className="mx-1 h-px w-6 bg-border" aria-hidden="true" />
              ) : null}
            </li>
          ))}
        </ol>

        {step === "details" ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="device-label">Label</Label>
              <Input
                id="device-label"
                placeholder="e.g. Greenhouse sensor"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                Shown in place of the default identifier (Req 5.4).
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="device-uid">Device UID (optional)</Label>
              <Input
                id="device-uid"
                placeholder="Hardware identity, auto-generated if blank"
                value={deviceUid}
                onChange={(e) => setDeviceUid(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="device-group">Group (optional)</Label>
              <select
                id="device-group"
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <option value="">No group</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : null}

        {step === "review" ? (
          <dl className="space-y-3 rounded-md border border-border p-4 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Label</dt>
              <dd className="font-medium">{label.trim() || "(default)"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Device UID</dt>
              <dd className="font-medium">
                {deviceUid.trim() || "(auto-generated)"}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Group</dt>
              <dd className="font-medium">
                {groups.find((g) => g.id === groupId)?.name || "No group"}
              </dd>
            </div>
          </dl>
        ) : null}

        {step === "done" && result ? (
          <div className="space-y-5">
            <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
              <CheckCircle size={18} weight="fill" />
              <span>
                Device{" "}
                <span className="font-medium">
                  {result.device.label || result.device.device_uid}
                </span>{" "}
                created.
              </span>
            </div>

            <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
                <WarningCircle size={16} />
                Device Token (save this — used to connect)
              </div>
              <div className="grid gap-2 text-sm">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-muted-foreground">Token</span>
                  <span className="flex items-center gap-2">
                    <code className="max-w-[14rem] truncate font-mono text-xs bg-muted px-2 py-1 rounded">
                      {result.mqtt_credentials?.device_token || result.device?.device_token || "(unavailable)"}
                    </code>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={copySecret}
                      aria-label="Copy token"
                    >
                      <Copy size={14} />
                    </Button>
                  </span>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground mt-2">
                Use this token as both MQTT username and password in your device firmware.
              </p>
            </div>

            <div className="space-y-2">
              <Label>Device QR code</Label>
              <QrDisplay
                deviceId={result.device.id}
                payload={result.qr}
                className="mx-auto"
              />
            </div>
          </div>
        ) : null}
      </DialogBody>

      <DialogFooter>
        {step === "details" ? (
          <>
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button onClick={() => setStep("review")}>Next</Button>
          </>
        ) : null}
        {step === "review" ? (
          <>
            <Button
              variant="outline"
              onClick={() => setStep("details")}
              disabled={submitting}
            >
              Back
            </Button>
            <Button onClick={onCreate} disabled={submitting}>
              {submitting ? "Provisioning..." : "Provision device"}
            </Button>
          </>
        ) : null}
        {step === "done" ? <Button onClick={handleClose}>Done</Button> : null}
      </DialogFooter>
    </Dialog>
  );
}
