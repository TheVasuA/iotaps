import { useCallback, useEffect, useState } from "react";
import { UsersThree, Plus, Buildings } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogBody } from "@/components/ui/dialog";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectUser, setCredentials } from "@/store/authSlice";
import { tokenStore } from "@/lib/apiClient";
import { principalFromToken } from "@/lib/authApi";
import { canManageOrgUsers, ACCOUNT_COMPANY } from "@/lib/accountTypes";
import {
  createOrgMember,
  getOrgProfile,
  listOrgMembers,
  upgradeToCompany,
} from "@/lib/orgApi";
import { refreshAccessToken } from "@/lib/sessionRefresh";

function roleLabel(role) {
  if (role === "project_center") return "Org admin";
  if (role === "device_user") return "Member";
  return role;
}

export default function OrgUsersPage() {
  const user = useAppSelector(selectUser);
  const dispatch = useAppDispatch();
  const [members, setMembers] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [upgradeName, setUpgradeName] = useState("");
  const [form, setForm] = useState({ email: "", password: "", role: "device_user" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await getOrgProfile();
      setProfile(p);
      if (p.can_manage_users) {
        const list = await listOrgMembers();
        setMembers(list);
      } else {
        setMembers([]);
      }
    } catch (err) {
      toast.error(err?.response?.data?.message || "Could not load organization users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const syncSessionAfterUpgrade = async () => {
    try {
      const access = await refreshAccessToken();
      const nextUser = principalFromToken(access);
      if (nextUser) {
        dispatch(
          setCredentials({
            user: nextUser,
            accessToken: access,
            refreshToken: tokenStore.getRefresh(),
          })
        );
      }
    } catch {
      /* ignore */
    }
  };

  const onUpgrade = async (e) => {
    e.preventDefault();
    if (!upgradeName.trim()) {
      toast.error("Enter your organization name");
      return;
    }
    try {
      await upgradeToCompany({ organizationName: upgradeName.trim() });
      toast.success("Upgraded to company organization");
      await syncSessionAfterUpgrade();
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.message || "Upgrade failed");
    }
  };

  const onCreate = async (e) => {
    e.preventDefault();
    try {
      await createOrgMember(form);
      toast.success("User created");
      setDialogOpen(false);
      setForm({ email: "", password: "", role: "device_user" });
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.message || "Could not create user");
    }
  };

  if (!canManageOrgUsers(user) && profile?.account_type !== ACCOUNT_COMPANY) {
    return (
      <div className="mx-auto max-w-lg space-y-6 py-8">
        <header>
          <h1 className="font-brand text-2xl font-bold">Organization users</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Individual and student accounts are single-user workspaces. Upgrade to a company
            organization when you are ready to invite teammates with their own console access.
          </p>
        </header>
        <form
          onSubmit={onUpgrade}
          className="rounded-xl border border-border bg-card p-6 space-y-4"
        >
          <div className="flex items-center gap-2 text-primary">
            <Buildings size={22} weight="duotone" />
            <h2 className="text-sm font-bold">Upgrade to company</h2>
          </div>
          <div className="space-y-2">
            <Label htmlFor="org-name">Organization name</Label>
            <Input
              id="org-name"
              value={upgradeName}
              onChange={(e) => setUpgradeName(e.target.value)}
              placeholder="Acme IoT Ltd"
              required
            />
          </div>
          <Button type="submit">Enable multi-user organization</Button>
        </form>
      </div>
    );
  }

  if (!canManageOrgUsers(user)) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Only organization admins can manage users.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 font-brand text-2xl font-bold">
            <UsersThree size={28} weight="duotone" className="text-primary" />
            Users
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {profile?.organization_name || user?.organization_name} — organization members
          </p>
        </div>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          <Plus size={18} className="mr-1" />
          Create new user
        </Button>
        <Dialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          title="Create organization user"
        >
          <DialogBody>
            <form className="space-y-4" onSubmit={onCreate}>
              <div className="space-y-2">
                <Label htmlFor="m-email">Email</Label>
                <Input
                  id="m-email"
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="m-password">Temporary password</Label>
                <Input
                  id="m-password"
                  type="password"
                  minLength={8}
                  required
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="m-role">Role</Label>
                <select
                  id="m-role"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={form.role}
                  onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                >
                  <option value="device_user">Member (devices & dashboards)</option>
                  <option value="project_center">Org admin</option>
                </select>
              </div>
              <Button type="submit" className="w-full">
                Create user
              </Button>
            </form>
          </DialogBody>
        </Dialog>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-semibold">Name</th>
              <th className="px-4 py-3 font-semibold">Email</th>
              <th className="px-4 py-3 font-semibold">Role</th>
              <th className="px-4 py-3 font-semibold">Organization</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : members.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                  No members yet.
                </td>
              </tr>
            ) : (
              members.map((m) => (
                <tr key={m.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium">
                    {m.email.split("@")[0]}
                    {m.is_org_owner ? (
                      <Badge variant="secondary" className="ml-2">
                        Owner
                      </Badge>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">{m.email}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{roleLabel(m.role)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {profile?.organization_name || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
