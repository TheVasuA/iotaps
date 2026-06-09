import { useState } from "react";
import { toast } from "sonner";
import { Buildings, UserGear, HardDrives } from "@phosphor-icons/react";
import {
  createCompany,
  suspendCompany,
  deleteCompany,
  resetUserPassword,
  changeUserRole,
  reassignDevice,
} from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Super_Admin companies / users / devices management panel (Task 20.7,
// Req 23.2-23.6). The backend admin surface is action-oriented (create, suspend,
// delete, reset-password, change-role, reassign) rather than list-based, so this
// panel exposes those operations as focused forms. Each call reports the API's
// outcome via toast.

const ROLES = ["super_admin", "project_center", "device_user"];

function PanelCard({ icon: Icon, title, description, children }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Icon size={20} className="text-primary" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export default function CompaniesPanel() {
  const [busy, setBusy] = useState(false);

  // Company create
  const [companyName, setCompanyName] = useState("");
  const [companyType, setCompanyType] = useState("project_center");
  // Company suspend / delete
  const [suspendId, setSuspendId] = useState("");
  const [deleteId, setDeleteId] = useState("");
  // User reset / role
  const [resetUserId, setResetUserId] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [roleUserId, setRoleUserId] = useState("");
  const [role, setRole] = useState("device_user");
  // Device reassign
  const [reassignId, setReassignId] = useState("");
  const [targetOrg, setTargetOrg] = useState("");

  const run = async (fn, successMsg) => {
    setBusy(true);
    try {
      await fn();
      toast.success(successMsg);
      return true;
    } catch (err) {
      toast.error(extractApiError(err).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="grid gap-6 xl:grid-cols-2">
      <PanelCard
        icon={Buildings}
        title="Create company"
        description="Provision a new company Organization (Req 23.2)."
      >
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(
              () => createCompany({ name: companyName, type: companyType }),
              "Company created"
            );
            if (ok) setCompanyName("");
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="company-name">Company name</Label>
            <Input
              id="company-name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="company-type">Type</Label>
            <select
              id="company-type"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={companyType}
              onChange={(e) => setCompanyType(e.target.value)}
            >
              <option value="project_center">Project center</option>
              <option value="device_user">Device user</option>
            </select>
          </div>
          <Button type="submit" disabled={busy || !companyName.trim()}>
            Create company
          </Button>
        </form>
      </PanelCard>

      <PanelCard
        icon={Buildings}
        title="Suspend or delete company"
        description="Suspend blocks new sign-ins; delete removes the org (Req 23.2, 23.3)."
      >
        <div className="space-y-4">
          <form
            className="flex items-end gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const ok = await run(
                () => suspendCompany(suspendId),
                "Company suspended"
              );
              if (ok) setSuspendId("");
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="suspend-id">Company ID</Label>
              <Input
                id="suspend-id"
                value={suspendId}
                onChange={(e) => setSuspendId(e.target.value)}
                placeholder="org uuid"
                required
              />
            </div>
            <Button type="submit" variant="secondary" disabled={busy || !suspendId.trim()}>
              Suspend
            </Button>
          </form>
          <form
            className="flex items-end gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const ok = await run(
                () => deleteCompany(deleteId),
                "Company deleted"
              );
              if (ok) setDeleteId("");
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="delete-id">Company ID</Label>
              <Input
                id="delete-id"
                value={deleteId}
                onChange={(e) => setDeleteId(e.target.value)}
                placeholder="org uuid"
                required
              />
            </div>
            <Button type="submit" variant="destructive" disabled={busy || !deleteId.trim()}>
              Delete
            </Button>
          </form>
        </div>
      </PanelCard>

      <PanelCard
        icon={UserGear}
        title="Reset user password"
        description="Reset a user's password across any organization (Req 23.4)."
      >
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(
              () => resetUserPassword(resetUserId, resetPassword),
              "Password reset"
            );
            if (ok) {
              setResetUserId("");
              setResetPassword("");
            }
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="reset-user-id">User ID</Label>
            <Input
              id="reset-user-id"
              value={resetUserId}
              onChange={(e) => setResetUserId(e.target.value)}
              placeholder="user uuid"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="reset-password">New password</Label>
            <Input
              id="reset-password"
              type="password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              minLength={8}
              required
            />
          </div>
          <Button
            type="submit"
            disabled={busy || !resetUserId.trim() || resetPassword.length < 8}
          >
            Reset password
          </Button>
        </form>
      </PanelCard>

      <PanelCard
        icon={UserGear}
        title="Change user role"
        description="Change a user's role and permissions (Req 23.5)."
      >
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(
              () => changeUserRole(roleUserId, role),
              "Role updated"
            );
            if (ok) setRoleUserId("");
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="role-user-id">User ID</Label>
            <Input
              id="role-user-id"
              value={roleUserId}
              onChange={(e) => setRoleUserId(e.target.value)}
              placeholder="user uuid"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <select
              id="role"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={busy || !roleUserId.trim()}>
            Change role
          </Button>
        </form>
      </PanelCard>

      <PanelCard
        icon={HardDrives}
        title="Reassign device"
        description="Move a device to another Organization across org boundaries (Req 23.6)."
      >
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(
              () => reassignDevice(reassignId, targetOrg),
              "Device reassigned"
            );
            if (ok) {
              setReassignId("");
              setTargetOrg("");
            }
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="reassign-id">Device ID</Label>
            <Input
              id="reassign-id"
              value={reassignId}
              onChange={(e) => setReassignId(e.target.value)}
              placeholder="device uuid"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-org">Target organization ID</Label>
            <Input
              id="target-org"
              value={targetOrg}
              onChange={(e) => setTargetOrg(e.target.value)}
              placeholder="org uuid"
              required
            />
          </div>
          <Button
            type="submit"
            disabled={busy || !reassignId.trim() || !targetOrg.trim()}
          >
            Reassign device
          </Button>
        </form>
      </PanelCard>
    </section>
  );
}
