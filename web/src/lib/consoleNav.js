import {
  House,
  RocketLaunch,
  SquaresFour,
  Table,
  Code,
  Cpu,
  FlowArrow,
  UsersThree,
  Buildings,
  MapPin,
  Camera,
  Truck,
  ChatCircle,
  ShieldCheck,
} from "@phosphor-icons/react";
import { canManageOrgUsers } from "@/lib/accountTypes";

/** Console sidebar — grouped categories (not a flat Blynk-style list). */
export const CONSOLE_NAV_GROUPS = [
  {
    id: "overview",
    label: "Overview",
    items: [{ to: "/get-started", label: "Get started", icon: RocketLaunch }],
  },
  {
    id: "monitor",
    label: "Monitor",
    items: [
      { to: "/dashboard", label: "Dashboards", icon: SquaresFour },
      { to: "/custom-data", label: "Custom data", icon: Table },
    ],
  },
  {
    id: "connect",
    label: "Connect",
    items: [
      { to: "/devices", label: "Devices", icon: Cpu },
      { to: "/flasher", label: "Developer zone", icon: Code },
      { to: "/fleet", label: "Fleet management", icon: Truck },
    ],
  },
  {
    id: "automate",
    label: "Automate",
    items: [{ to: "/rules", label: "Automations", icon: FlowArrow }],
  },
  {
    id: "workspace",
    label: "Workspace",
    items: [
      {
        to: "/org/users",
        label: "Users",
        icon: UsersThree,
        title: "Organization members (company)",
        requiresOrgAdmin: true,
      },
      { to: "/organizations", label: "Organizations", icon: Buildings, title: "Org workspace" },
      { to: "/support", label: "Support", icon: ChatCircle, title: "Help & chat" },
    ],
  },
  {
    id: "advanced",
    label: "Advanced",
    items: [
      { to: "/locations", label: "Locations", icon: MapPin },
      { to: "/snapshots", label: "Snapshots", icon: Camera },
    ],
  },
];

export const CONSOLE_ADMIN_NAV = {
  to: "/admin",
  label: "Platform admin",
  icon: ShieldCheck,
  title: "Super-admin control panel",
};

export function getConsoleNavGroups(user, role, { hasHomepage = false } = {}) {
  const groups = CONSOLE_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.requiresOrgAdmin || item.to === "/org/users") {
        return canManageOrgUsers(user);
      }
      return true;
    }),
  })).filter((group) => group.items.length > 0);

  if (hasHomepage) {
    const overview = groups.find((group) => group.id === "overview");
    if (overview) {
      const afterStart = overview.items.findIndex((item) => item.to === "/get-started");
      overview.items.splice(afterStart + 1, 0, {
        to: "/homepage",
        label: "Homepage",
        icon: House,
      });
    }
  }

  if (role === "super_admin") {
    groups.push({
      id: "platform",
      label: "Platform",
      items: [CONSOLE_ADMIN_NAV],
    });
  }

  return groups;
}
