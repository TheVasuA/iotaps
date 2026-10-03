import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Info, Rocket, User, X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { getDashboardAccess, saveDashboardAccess } from "@/lib/dashboardsApi";

const ROOT_ROLES = [
  { id: "admin", label: "Admin", roles: ["project_center", "super_admin"], grant: "edit" },
  { id: "staff", label: "Staff", roles: [], grant: "view" },
  { id: "user", label: "User", roles: ["device_user"], grant: "view" },
];

const SUB_ROLES = [
  { id: "admin", label: "Admin" },
  { id: "staff", label: "Staff" },
  { id: "user", label: "User" },
];

function countLabel(count) {
  return count === 1 ? "1 user" : `${count} users`;
}

function AccessSwitch({ checked, disabled, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => !disabled && onChange?.(!checked)}
      className={cn("dash-access-switch", checked && "dash-access-switch-on", disabled && "opacity-50")}
    >
      <span />
    </button>
  );
}

/** Blynk-style access drawer: role toggles for this workspace, upgrade for sub-organizations. */
export default function DashboardAccessDrawer({ open, dashboardId, onClose }) {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !dashboardId) return undefined;
    let cancelled = false;
    setLoading(true);
    getDashboardAccess(dashboardId)
      .then((data) => {
        if (!cancelled) setMembers(data.members || []);
      })
      .catch((err) => {
        if (!cancelled) toast.error(err?.response?.data?.message || "Could not load access");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, dashboardId]);

  const groups = useMemo(
    () =>
      ROOT_ROLES.map((group) => {
        const people = members.filter((member) => group.roles.includes(member.role));
        const others = people.filter((member) => !member.is_owner);
        const enabled =
          people.length > 0 &&
          (others.length === 0
            ? people.some((member) => member.is_owner)
            : others.every((member) => (group.grant === "edit" ? member.can_edit : member.can_view || member.can_edit)));
        return { ...group, count: people.length, enabled, locked: people.length === 0 };
      }),
    [members]
  );

  if (!open) return null;

  const persist = async (nextMembers) => {
    setSaving(true);
    try {
      const viewers = nextMembers
        .filter((row) => row.can_view && !row.can_edit && !row.is_owner)
        .map((row) => row.id);
      const editors = nextMembers.filter((row) => row.can_edit && !row.is_owner).map((row) => row.id);
      const saved = await saveDashboardAccess(dashboardId, { viewers, editors });
      setMembers(saved.members || nextMembers);
    } catch (err) {
      toast.error(err?.response?.data?.message || "Could not save access");
    } finally {
      setSaving(false);
    }
  };

  const toggleRole = (group, next) => {
    if (group.locked) return;
    const others = members.filter((member) => group.roles.includes(member.role) && !member.is_owner);
    if (others.length === 0) {
      toast.info("You already have access as the owner");
      return;
    }
    const nextMembers = members.map((member) => {
      if (member.is_owner || !group.roles.includes(member.role)) return member;
      if (!next) return { ...member, can_view: false, can_edit: false };
      if (group.grant === "edit") return { ...member, can_view: true, can_edit: true };
      return { ...member, can_view: true, can_edit: false };
    });
    setMembers(nextMembers);
    persist(nextMembers);
  };

  return (
    <div className="dash-access-root" role="presentation">
      <button type="button" className="dash-access-backdrop" aria-label="Close" onClick={onClose} />
      <aside className="dash-access-drawer" role="dialog" aria-modal="true" aria-label="Manage Access">
        <header className="dash-access-header">
          <button type="button" className="dash-access-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
          <h2>Manage Access</h2>
        </header>
        <div className="dash-access-body">
          {loading ? (
            <p className="px-6 py-6 text-sm text-muted-foreground">Loading access…</p>
          ) : (
            <div className="dash-access-sections">
              <section>
                <h3>Root organization users</h3>
                <p>Specify who in the organization can access this dashboard</p>
                <ul>
                  {groups.map((group) => (
                    <li key={group.id}>
                      <span className="dash-access-role">
                        <User size={18} />
                        {group.label}
                        <em>({countLabel(group.count)})</em>
                      </span>
                      <AccessSwitch
                        checked={group.enabled}
                        disabled={saving || group.locked}
                        label={group.label}
                        onChange={(next) => toggleRole(group, next)}
                      />
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3>Sub-organizations users</h3>
                <p>Make this dashboard visible in sub-organizations</p>
                <ul>
                  {SUB_ROLES.map((group) => (
                    <li key={group.id}>
                      <span className="dash-access-role">
                        <User size={18} />
                        {group.label}
                      </span>
                      <AccessSwitch checked={false} disabled label={group.label} />
                    </li>
                  ))}
                </ul>
                <div className="dash-access-note">
                  <Info size={16} />
                  <span>Changes made to this dashboard will apply to all sub-organizations.</span>
                </div>
              </section>
            </div>
          )}
        </div>
        <footer className="dash-access-footer">
          <Link to="/billing" className="dash-access-upgrade-btn">
            <Rocket size={16} weight="fill" />
            Upgrade To Unlock Feature
          </Link>
        </footer>
      </aside>
    </div>
  );
}
