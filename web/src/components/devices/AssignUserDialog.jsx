import { useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "@phosphor-icons/react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppDispatch } from "@/store/hooks";
import { assignDeviceToUser } from "@/store/devicesSlice";

// Assign a device to a Device_User (Req 5.6). The backend grants that user
// access to this device only. The device user is identified by id (UUID); the
// admin user-directory picker is built in the admin task (20.7), so this takes
// the user id directly.
export default function AssignUserDialog({ open, onClose, device }) {
  const dispatch = useAppDispatch();
  const [userId, setUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    const trimmed = userId.trim();
    if (!trimmed || !device) return;
    setSubmitting(true);
    try {
      await dispatch(
        assignDeviceToUser({ id: device.id, userId: trimmed })
      ).unwrap();
      toast.success("Device assigned to user");
      setUserId("");
      onClose?.();
    } catch (err) {
      toast.error(err?.message || "Failed to assign device");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Assign device to user"
      description={
        device
          ? `Grant a Device User access to "${device.label || device.device_uid}".`
          : undefined
      }
    >
      <form onSubmit={onSubmit}>
        <DialogBody className="space-y-2">
          <Label htmlFor="assign-user-id">Device User ID</Label>
          <Input
            id="assign-user-id"
            placeholder="User UUID"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            autoFocus
          />
          <p className="text-xs text-muted-foreground">
            The user will be granted access to this device only (Req 5.6).
          </p>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting || !userId.trim()}>
            <UserPlus size={16} />
            {submitting ? "Assigning..." : "Assign"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
