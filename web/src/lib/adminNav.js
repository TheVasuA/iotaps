import {
  ChartPie,
  Gauge,
  Heartbeat,
  Buildings,
  Users,
  DeviceMobile,
  HardDrives,
  Lifebuoy,
  Wrench,
  CurrencyInr,
  Tag,
  Timer,
  FileText,
  ShieldCheck,
  Terminal,
} from "@phosphor-icons/react";

export const ADMIN_NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      { to: "/admin", end: true, label: "Dashboard", icon: ChartPie },
      { to: "/admin/system", label: "System stats", icon: Gauge },
      { to: "/admin/health", label: "Health & errors", icon: Heartbeat },
    ],
  },
  {
    label: "Tenants & fleet",
    items: [
      { to: "/admin/companies", label: "Organizations", icon: Buildings },
      { to: "/admin/users", label: "Users & roles", icon: Users },
      { to: "/admin/devices-overview", label: "All devices", icon: DeviceMobile },
    ],
  },
  {
    label: "Infrastructure",
    items: [
      { to: "/admin/mqtt-nodes", label: "MQTT nodes", icon: HardDrives },
      { to: "/admin/recovery", label: "Disaster recovery", icon: Lifebuoy },
      { to: "/admin/controls", label: "Platform controls", icon: Wrench },
    ],
  },
  {
    label: "Business & content",
    items: [
      { to: "/admin/revenue", label: "Revenue", icon: CurrencyInr },
      { to: "/admin/coupons", label: "Coupons", icon: Tag },
      { to: "/admin/expiring", label: "Expiring plans", icon: Timer },
      { to: "/admin/content", label: "Templates & CMS", icon: FileText },
      { to: "/admin/security", label: "Security audit", icon: ShieldCheck },
      { to: "/admin/commands", label: "API commands", icon: Terminal },
    ],
  },
];

/** Hub cards on /admin home — maps console areas to admin tools. */
export const ADMIN_HUB_SECTIONS = [
  {
    title: "Tenants & access",
    description: "Organizations, user roles, password resets, suspensions.",
    to: "/admin/companies",
    cta: "Manage orgs",
  },
  {
    title: "Fleet & devices",
    description: "Cross-tenant device list, reassignment, online counts.",
    to: "/admin/devices-overview",
    cta: "All devices",
  },
  {
    title: "Billing & growth",
    description: "Revenue, coupons, expiring subscriptions, referrals.",
    to: "/admin/revenue",
    cta: "Revenue",
  },
  {
    title: "MQTT infrastructure",
    description: "Broker nodes, connections, capacity and failover.",
    to: "/admin/mqtt-nodes",
    cta: "MQTT nodes",
  },
  {
    title: "Content & notifications",
    description: "Device templates, notification settings, site analytics.",
    to: "/admin/content",
    cta: "Content",
  },
  {
    title: "Security & compliance",
    description: "Audit log, security settings, platform-wide policies.",
    to: "/admin/security",
    cta: "Security",
  },
  {
    title: "Operations",
    description: "Backups, restore, marketing toggles, resource limits.",
    to: "/admin/controls",
    cta: "Controls",
  },
  {
    title: "Reliability",
    description: "Error feeds, degraded services, disaster recovery runbooks.",
    to: "/admin/health",
    cta: "Health",
  },
];

export const ADMIN_ROUTE_TITLES = {
  "/admin": "Platform admin",
  "/admin/system": "System stats",
  "/admin/health": "Health & errors",
  "/admin/companies": "Organizations",
  "/admin/users": "Users & roles",
  "/admin/devices-overview": "All devices",
  "/admin/mqtt-nodes": "MQTT nodes",
  "/admin/recovery": "Disaster recovery",
  "/admin/controls": "Platform controls",
  "/admin/revenue": "Revenue",
  "/admin/coupons": "Coupons",
  "/admin/expiring": "Expiring plans",
  "/admin/content": "Templates & CMS",
  "/admin/security": "Security audit",
  "/admin/commands": "API commands",
};

export function adminTitleForPath(pathname) {
  if (ADMIN_ROUTE_TITLES[pathname]) return ADMIN_ROUTE_TITLES[pathname];
  if (pathname.startsWith("/admin")) return "Platform admin";
  return null;
}
