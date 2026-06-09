import { useState } from "react";
import { toast } from "sonner";
import { FolderPlus, Stack } from "@phosphor-icons/react";
import { Dialog, DialogBody, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  createDeviceGroup,
  selectDeviceGroups,
  selectDevices,
} from "@/store/devicesSlice";

// Device group management (Req 5.5). Lists existing groups with their device
// counts and lets a Project_Center create a new group. Adding devices to a
// group happens from the device editor (PATCH group_id); this surface owns
// group creation + an overview.
export default function GroupManager({ open, onClose }) {
  const dispatch = useAppDispatch();
  const groups = useAppSelector(selectDeviceGroups);
  const devices = useAppSelector(selectDevices);

  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const countForGroup = (groupId) =>
    devices.filter((d) => d.group_id === groupId).length;

  const onCreate = async (e) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await dispatch(createDeviceGroup(trimmed)).unwrap();
      toast.success(`Group "${trimmed}" created`);
      setName("");
    } catch (err) {
      toast.error(err?.message || "Failed to create group");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Device groups"
      description="Organize devices into groups for easier fleet management."
    >
      <DialogBody className="space-y-5">
        <form className="flex items-end gap-2" onSubmit={onCreate}>
          <div className="flex-1 space-y-2">
            <Label htmlFor="group-name">New group name</Label>
            <Input
              id="group-name"
              placeholder="e.g. Warehouse A"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting || !name.trim()}>
            <FolderPlus size={16} />
            Add
          </Button>
        </form>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">
            Existing groups
          </p>
          {groups.length === 0 ? (
            <p className="rounded-md border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
              No groups yet. Create one above.
            </p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {groups.map((g) => (
                <li
                  key={g.id}
                  className="flex items-center justify-between px-4 py-2.5 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <Stack size={16} className="text-muted-foreground" />
                    {g.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {countForGroup(g.id)} device
                    {countForGroup(g.id) === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogBody>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
