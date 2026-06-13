import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash, CaretDown, CaretRight } from "@phosphor-icons/react";
import { getUsers, deleteUser } from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

// Super_Admin user management panel. Lists all platform users with device
// counts and subscription status. Supports role filtering, inline deletion,
// and expandable rows showing user details.

const ROLES = ["all", "super_admin", "project_center", "device_user"];

export default function UsersPanel() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);
  const [busy, setBusy] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await getUsers();
      setUsers(data);
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleDelete = async (userId, email) => {
    if (!window.confirm(`Delete user "${email}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await deleteUser(userId);
      toast.success(`User ${email} deleted`);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const filtered =
    roleFilter === "all" ? users : users.filter((u) => u.role === roleFilter);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Platform Users</CardTitle>
        <CardDescription>
          All registered users with device counts and subscription status.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* Role filter */}
        <div className="mb-4 flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Filter by role:</span>
          <select
            className="flex h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            aria-label="Filter users by role"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r === "all" ? "All roles" : r}
              </option>
            ))}
          </select>
          <span className="ml-auto text-xs text-muted-foreground">
            {filtered.length} user{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No users found.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="w-8 px-2 py-2" />
                  <th className="px-2 py-2">Email</th>
                  <th className="px-2 py-2">Role</th>
                  <th className="px-2 py-2 text-right">Devices</th>
                  <th className="px-2 py-2 text-right">Subscription</th>
                  <th className="px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((user) => {
                  const isExpanded = expandedId === user.id;
                  const expiring =
                    user.subscription_days_remaining !== null &&
                    user.subscription_days_remaining < 7;

                  return (
                    <>
                      <tr
                        key={user.id}
                        className="cursor-pointer border-b transition-colors hover:bg-muted/50"
                        onClick={() =>
                          setExpandedId(isExpanded ? null : user.id)
                        }
                      >
                        <td className="px-2 py-2">
                          {isExpanded ? (
                            <CaretDown size={14} />
                          ) : (
                            <CaretRight size={14} />
                          )}
                        </td>
                        <td className="px-2 py-2 font-medium">{user.email}</td>
                        <td className="px-2 py-2">
                          <Badge variant="secondary">{user.role}</Badge>
                        </td>
                        <td className="px-2 py-2 text-right">
                          {user.device_count}
                        </td>
                        <td className="px-2 py-2 text-right">
                          {user.subscription_days_remaining !== null ? (
                            <span className="inline-flex items-center gap-1.5">
                              {user.subscription_days_remaining}d
                              {expiring && (
                                <Badge
                                  className="bg-red-500/15 text-red-600 dark:text-red-400"
                                >
                                  Expiring
                                </Badge>
                              )}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:bg-destructive/10"
                            disabled={busy}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(user.id, user.email);
                            }}
                            aria-label={`Delete user ${user.email}`}
                          >
                            <Trash size={16} />
                          </Button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${user.id}-detail`} className="border-b bg-muted/30">
                          <td />
                          <td colSpan={5} className="px-2 py-3">
                            <div className="grid gap-1 text-xs">
                              <p>
                                <span className="text-muted-foreground">ID:</span>{" "}
                                <code className="rounded bg-muted px-1">{user.id}</code>
                              </p>
                              <p>
                                <span className="text-muted-foreground">Org ID:</span>{" "}
                                <code className="rounded bg-muted px-1">{user.org_id}</code>
                              </p>
                              <p>
                                <span className="text-muted-foreground">Created:</span>{" "}
                                {user.created_at || "—"}
                              </p>
                              <p>
                                <span className="text-muted-foreground">Devices:</span>{" "}
                                {user.device_count}
                              </p>
                              <p>
                                <span className="text-muted-foreground">
                                  Subscription days remaining:
                                </span>{" "}
                                {user.subscription_days_remaining ?? "No active subscription"}
                              </p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
