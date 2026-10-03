import {
  RocketLaunch,
  SquaresFour,
  Cpu,
  Broadcast,
  Lightning,
  FlowArrow,
  CreditCard,
  Gift,
  Wallet,
  Headset,
  ShieldCheck,
} from "@phosphor-icons/react";

/** Authenticated app navigation — grouped like ThingsBoard entity sections. */
export const APP_NAV_GROUPS = [
  {
    label: "Console",
    items: [
      {
        to: "/get-started",
        label: "Get started",
        icon: RocketLaunch,
        description: "Onboarding & plan overview",
      },
    ],
  },
  {
    label: "Monitoring",
    items: [
      { to: "/dashboard", label: "Dashboards", icon: SquaresFour, description: "Live widgets & telemetry" },
      { to: "/explorer", label: "IoT Explorer", icon: Broadcast, description: "MQTT topic browser" },
    ],
  },
  {
    label: "Fleet",
    items: [
      { to: "/devices", label: "Devices", icon: Cpu, description: "Provision & manage devices" },
      { to: "/flasher", label: "Web Flasher", icon: Lightning, description: "Flash firmware over serial" },
    ],
  },
  {
    label: "Automation",
    items: [
      { to: "/rules", label: "Rule chains", icon: FlowArrow, description: "Visual flows (Node-RED style)" },
    ],
  },
  {
    label: "Account",
    items: [
      { to: "/billing", label: "Billing", icon: CreditCard },
      { to: "/referrals", label: "Referrals", icon: Gift },
      { to: "/wallet", label: "Wallet", icon: Wallet },
      { to: "/support", label: "Support", icon: Headset },
    ],
  },
];

export const ADMIN_NAV_ITEM = {
  to: "/admin",
  label: "Platform admin",
  icon: ShieldCheck,
  description: "Super-admin control panel",
};

/** Route path → page title for the top bar. */
export const ROUTE_TITLES = {
  "/get-started": "Get started",
  "/dashboard": "Dashboards",
  "/homepage": "Homepage",
  "/devices": "Devices",
  "/flasher": "Web Flasher",
  "/explorer": "IoT Explorer",
  "/custom-data": "Custom data",
  "/locations": "Locations",
  "/organizations": "Organizations",
  "/snapshots": "Snapshots",
  "/fleet": "Fleet management",
  "/rules": "Rule chains",
  "/billing": "Billing",
  "/referrals": "Referrals",
  "/wallet": "Partner wallet",
  "/support": "Support",
  "/org/users": "Users",
  "/settings": "Account settings",
};

export function titleForPathname(pathname) {
  if (ROUTE_TITLES[pathname]) return ROUTE_TITLES[pathname];
  if (pathname.startsWith("/devices/")) return "Device details";
  if (pathname.startsWith("/rules/")) return "Rule editor";
  if (pathname.startsWith("/admin")) return "Platform admin";
  return "IoTAPS";
}
