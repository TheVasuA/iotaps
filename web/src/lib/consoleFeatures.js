import { Table, MapPin, Buildings, Camera, Truck } from "@phosphor-icons/react";

/** Marketing-style feature shells until full product UI ships. */
export const CONSOLE_FEATURES = {
  "custom-data": {
    slug: "custom-data",
    title: "Custom data",
    eyebrow: "Structured telemetry",
    description:
      "Model tables, metadata fields, and queryable datasets alongside live MQTT streams — so dashboards and automations can use more than raw topic payloads.",
    bullets: [
      "Define schemas and bind device properties to columns",
      "Export and API access for analytics pipelines",
      "Join custom tables with dashboard widgets and rules",
    ],
    badge: "Rolling out on Pro",
    badgeVariant: "pro",
    icon: Table,
    primaryCta: { label: "Open MQTT explorer", to: "/explorer" },
    secondaryCta: { label: "View billing", to: "/billing" },
  },
  locations: {
    slug: "locations",
    title: "Locations",
    eyebrow: "Sites & geography",
    description:
      "Organize devices by site, region, or floor plan. Map views and location-aware automations help teams manage distributed fleets from one console.",
    bullets: [
      "Hierarchy of sites, buildings, and zones",
      "Assign devices and dashboards per location",
      "Geo context for alerts and maintenance workflows",
    ],
    badge: "In development",
    badgeVariant: "soon",
    icon: MapPin,
    primaryCta: { label: "Manage devices", to: "/devices" },
    secondaryCta: { label: "Contact sales", to: "/contact" },
  },
  organizations: {
    slug: "organizations",
    title: "Organizations",
    eyebrow: "Multi-tenant workspace",
    description:
      "Run multiple teams, billing entities, and device estates under one IoTAPS account — with clear ownership, usage limits, and admin controls.",
    bullets: [
      "Company workspaces with invited operators",
      "Central billing and plan limits per organization",
      "Audit-friendly separation between projects",
    ],
    badge: "Company plans",
    badgeVariant: "company",
    icon: Buildings,
    primaryCta: { label: "Billing & plans", to: "/billing" },
    secondaryCta: { label: "Manage users", to: "/org/users" },
  },
  snapshots: {
    slug: "snapshots",
    title: "Snapshots",
    eyebrow: "Historical traceability",
    description:
      "Never lose valuable insights. Snapshots preserve device history and configuration context even after hardware is retired — so you keep full traceability for compliance and support.",
    bullets: [
      "Point-in-time captures of telemetry and metadata",
      "Restore context when troubleshooting deleted devices",
      "Long-retention archives for enterprise deployments",
    ],
    badge: "Enterprise preview",
    badgeVariant: "enterprise",
    icon: Camera,
    primaryCta: { label: "Talk to support", to: "/support" },
    secondaryCta: { label: "Enterprise overview", to: "/enterprise" },
  },
  fleet: {
    slug: "fleet",
    title: "Fleet management",
    eyebrow: "Operations at scale",
    description:
      "Monitor health across hundreds of devices, group firmware targets, and roll out changes safely — without leaving the IoTAPS console.",
    bullets: [
      "Fleet-wide status, last-seen, and alert rollups",
      "Bulk actions and staged firmware campaigns",
      "Tags and segments tied to automations",
    ],
    badge: "Preview",
    badgeVariant: "pro",
    icon: Truck,
    primaryCta: { label: "Open devices", to: "/devices" },
    secondaryCta: { label: "Developer zone", to: "/flasher" },
  },
};

export const CONSOLE_FEATURES_BY_PATH = Object.fromEntries(
  Object.values(CONSOLE_FEATURES).map((f) => [`/${f.slug}`, f])
);
