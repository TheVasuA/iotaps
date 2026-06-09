import { PublicPage, PageHeader, Prose } from "@/components/public/PublicPage";

// Public Privacy Policy page (Task 21.1, Req 31.1).
const sections = [
  {
    heading: "1. Information we collect",
    body: [
      "We collect account information (such as your email), device telemetry you publish to the platform, and usage data needed to operate the service.",
    ],
  },
  {
    heading: "2. How we use information",
    body: [
      "We use your information to provide and improve the platform, deliver notifications you enable, process payments, and maintain security.",
    ],
  },
  {
    heading: "3. Data isolation",
    body: [
      "All tenant data is associated with your organization and isolated from other organizations. We do not share your device data across tenants.",
    ],
  },
  {
    heading: "4. Data retention",
    body: [
      "Telemetry is retained according to your plan. Expired telemetry is deleted automatically once it exceeds your plan's retention period.",
    ],
  },
  {
    heading: "5. Your choices",
    body: [
      "You can configure which notification channels are enabled and request deletion of your account data, subject to legal and operational requirements.",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <PublicPage>
      <PageHeader title="Privacy Policy" subtitle="How we collect, use, and protect your data." />
      <Prose sections={sections} />
    </PublicPage>
  );
}
