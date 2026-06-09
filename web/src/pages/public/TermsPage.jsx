import { PublicPage, PageHeader, Prose } from "@/components/public/PublicPage";

// Public Terms of Service page (Task 21.1, Req 31.1).
const sections = [
  {
    heading: "1. Acceptance of terms",
    body: [
      "By creating an account or using IoTAPS, you agree to these Terms of Service. If you do not agree, do not use the platform.",
    ],
  },
  {
    heading: "2. Accounts and access",
    body: [
      "You are responsible for safeguarding your credentials and for all activity under your account. Access is governed by your assigned role and your organization's data isolation boundary.",
    ],
  },
  {
    heading: "3. Acceptable use",
    body: [
      "You agree not to misuse the platform, interfere with its operation, or attempt to access data belonging to other organizations.",
    ],
  },
  {
    heading: "4. Subscriptions and billing",
    body: [
      "Paid plans are billed per device on a monthly or annual basis. Plan limits and entitlements apply according to your active subscription tier.",
    ],
  },
  {
    heading: "5. Changes to the service",
    body: [
      "We may update features and these terms over time. Material changes will be communicated through the platform changelog.",
    ],
  },
];

export default function TermsPage() {
  return (
    <PublicPage>
      <PageHeader title="Terms of Service" subtitle="Last updated: the date shown in your account region." />
      <Prose sections={sections} />
    </PublicPage>
  );
}
