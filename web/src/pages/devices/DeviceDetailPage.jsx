import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  FloppyDisk,
  Trash,
  UserPlus,
  CircleNotch,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  fetchDevices,
  saveDevice,
  removeDevice,
  upsertDevice,
  selectDeviceById,
  selectDeviceGroups,
  selectDevices,
} from "@/store/devicesSlice";
import { getDevice } from "@/lib/devicesApi";
import { extractApiError } from "@/lib/authApi";
import QrDisplay from "@/components/devices/QrDisplay";
import AssignUserDialog from "@/components/devices/AssignUserDialog";
import ToggleControl from "@/components/devices/ToggleControl";
import SliderControl from "@/components/devices/SliderControl";

// Device detail view (Req 5.3, 5.4, 5.5, 5.6, 5.7): rename, reassign group,
// toggle maintenance mode, assign to a Device User, view the QR code, and
// delete the device (which revokes its MQTT credentials, Req 5.9).
export default function DeviceDetailPage() {
  const { id } = useParams();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const device = useAppSelector(selectDeviceById(id));
  const groups = useAppSelector(selectDeviceGroups);
  const allDevices = useAppSelector(selectDevices);

  const [label, setLabel] = useState("");
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Ensure the device is in the cache; fetch the list if we landed here directly.
  useEffect(() => {
    if (!device && allDevices.length === 0) {
      dispatch(fetchDevices());
    }
  }, [dispatch, device, allDevices.length]);

  // If still missing after the list load, fetch the single device directly.
  useEffect(() => {
    let active = true;
    if (!device && id) {
      setLoading(true);
      getDevice(id)
        .then((d) => {
          if (active) dispatch(upsertDevice(d));
        })
        .catch((err) => {
          if (active) toast.error(extractApiError(err).message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Sync the editable fields when the device loads/changes.
  useEffect(() => {
    if (device) {
      setLabel(device.label || "");
      setGroupId(device.group_id || "");
    }
  }, [device]);

  if (loading && !device) {
    return (
      <div className="flex justify-center py-20 text-muted-foreground">
        <CircleNotch size={24} className="animate-spin" />
      </div>
    );
  }

  if (!device) {
    return (
      <section className="mx-auto max-w-2xl space-y-3 rounded-lg border border-border bg-card p-8 text-card-foreground">
        <h1 className="text-2xl font-semibold text-primary">Device not found</h1>
        <p className="text-sm text-muted-foreground">
          This device does not exist or is outside your organization.
        </p>
        <Button variant="outline" onClick={() => navigate("/devices")}>
          <ArrowLeft size={16} />
          Back to devices
        </Button>
      </section>
    );
  }

  const dirty =
    label !== (device.label || "") || groupId !== (device.group_id || "");

  const onSaveDetails = async () => {
    setSaving(true);
    try {
      await dispatch(
        saveDevice({
          id: device.id,
          changes: { label: label.trim() || null, groupId: groupId || null },
        })
      ).unwrap();
      toast.success("Device updated");
    } catch (err) {
      toast.error(err?.message || "Failed to update device");
    } finally {
      setSaving(false);
    }
  };

  const onToggleMaintenance = async (next) => {
    try {
      await dispatch(
        saveDevice({ id: device.id, changes: { maintenanceMode: next } })
      ).unwrap();
      toast.success(
        next ? "Maintenance mode enabled" : "Maintenance mode disabled"
      );
    } catch (err) {
      toast.error(err?.message || "Failed to toggle maintenance mode");
    }
  };

  const onDelete = async () => {
    setDeleting(true);
    try {
      await dispatch(removeDevice(device.id)).unwrap();
      toast.success("Device deleted");
      navigate("/devices");
    } catch (err) {
      toast.error(err?.message || "Failed to delete device");
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <section className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Back"
            onClick={() => navigate("/devices")}
          >
            <ArrowLeft size={18} />
          </Button>
          <div>
            <h1 className="text-2xl font-semibold text-primary">
              {device.label || device.device_uid || "Device"}
            </h1>
            <p className="text-sm text-muted-foreground">{device.device_uid}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={device.status === "online" ? "success" : "muted"}>
            {device.status}
          </Badge>
          {device.maintenance_mode ? (
            <Badge variant="warning">Maintenance</Badge>
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="space-y-6 md:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Details</CardTitle>
              <CardDescription>
                Rename the device and assign it to a group (Req 5.3-5.5).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="detail-label">Label</Label>
                <Input
                  id="detail-label"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder={device.device_uid}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="detail-group">Group</Label>
                <select
                  id="detail-group"
                  value={groupId}
                  onChange={(e) => setGroupId(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <option value="">No group</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Button onClick={onSaveDetails} disabled={!dirty || saving}>
                  <FloppyDisk size={16} />
                  {saving ? "Saving..." : "Save changes"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Controls</CardTitle>
              <CardDescription>
                Send commands to this device. Feedback shows when the device
                confirms or fails to acknowledge a command (Req 9.1, 9.2, 9.4).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <ToggleControl
                deviceId={device.id}
                deviceLabel={device.label || device.device_uid}
                label="Power"
              />
              <SliderControl
                deviceId={device.id}
                deviceLabel={device.label || device.device_uid}
                label="Level"
                min={0}
                max={255}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Maintenance mode</CardTitle>
              <CardDescription>
                While enabled, alert evaluation and notifications are suppressed
                for this device (Req 5.7).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <Label htmlFor="maintenance-toggle">
                {device.maintenance_mode ? "Enabled" : "Disabled"}
              </Label>
              <Switch
                id="maintenance-toggle"
                checked={device.maintenance_mode}
                onChange={onToggleMaintenance}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Access</CardTitle>
              <CardDescription>
                Assign this device to a Device User (Req 5.6).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => setAssignOpen(true)}>
                <UserPlus size={16} />
                Assign to user
              </Button>
            </CardContent>
          </Card>

          <Card className="border-destructive/40">
            <CardHeader>
              <CardTitle className="text-lg text-destructive">
                Danger zone
              </CardTitle>
              <CardDescription>
                Deleting a device removes it and revokes its MQTT credentials
                (Req 5.9). This cannot be undone.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                variant="destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash size={16} />
                Delete device
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">QR code</CardTitle>
            <CardDescription>Encodes the device identity (Req 5.2).</CardDescription>
          </CardHeader>
          <CardContent>
            <QrDisplay deviceId={device.id} className="mx-auto" />
          </CardContent>
        </Card>
      </div>

      <AssignUserDialog
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        device={device}
      />

      <Dialog
        open={confirmDelete}
        onClose={() => !deleting && setConfirmDelete(false)}
        title="Delete device?"
        description={`"${device.label || device.device_uid}" will be permanently removed and its MQTT credentials revoked.`}
      >
        <DialogBody className="text-sm text-muted-foreground">
          This action cannot be undone.
        </DialogBody>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setConfirmDelete(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button variant="destructive" onClick={onDelete} disabled={deleting}>
            <Trash size={16} />
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </Dialog>
    </section>
  );
}
