import { PublicPage, PageHeader, Prose } from "@/components/public/PublicPage";

// Public Refund Policy page (Task 21.1, Req 31.1). Reflects the 14-day
// money-back guarantee enforced by the billing service (Req 17.5, 17.7).
const sections = [
  {
    heading: "14-day money-back guarantee",
    body: [
      "If you are not satisfied with a Pro subscription, you may request a refund within 14 days of purchase. Approved refunds are processed back to your original payment method through our payment gateway.",
    ],
  },
  {
    heading: "After the 14-day window",
    body: [
      "Refund requests made after the 14-day window has elapsed are not eligible and will be declined.",
    ],
  },
  {
    heading: "How to request a refund",
    body: [
      "Signed-in customers can request a refund from the Billing page in the app. The request is evaluated against the 14-day window automatically.",
    ],
  },
  {
    heading: "Auto-renewals",
    body: [
      "For recurring subscriptions with auto-debit enabled, you can cancel before the renewal date to avoid the next charge.",
    ],
  },
];

export default function RefundPolicyPage() {
  return (
    <PublicPage>
      <PageHeader title="Refund Policy" subtitle="Our money-back guarantee and how refunds work." />
      <Prose sections={sections} />
    </PublicPage>
  );
}
