import { PublicPage, PageHeader } from "@/components/public/PublicPage";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

// Public FAQ page (Task 21.1, Req 31.1).
const faqs = [
  {
    question: "What devices does IoTAPS support?",
    answer:
      "IoTAPS supports ESP32 and ESP8266 hardware, plus virtual device simulators for building and testing dashboards without physical hardware.",
  },
  {
    question: "Is there a free plan?",
    answer:
      "Yes. The Free plan includes 2 devices, 20,000 messages per month, 7 days of data retention, 10 sensors, and 2 rules with view-only device access.",
  },
  {
    question: "How does Pro pricing work?",
    answer:
      "Pro is priced per device per month with volume discounts as your fleet grows, or a fixed annual price per device. You can size a quote on the Pricing page.",
  },
  {
    question: "How do referrals work?",
    answer:
      "Refer friends to earn free Pro device-months. Six successful referrals earns 3 devices free for 3 months with all Pro features included.",
  },
  {
    question: "Can I get a refund?",
    answer:
      "Yes. We offer a 14-day money-back guarantee on Pro subscriptions. See our Refund Policy for details.",
  },
  {
    question: "Can I share a dashboard publicly?",
    answer:
      "Yes. You can enable a read-only public link for any dashboard so others can view device data without signing in.",
  },
];

export default function FaqPage() {
  return (
    <PublicPage>
      <PageHeader
        title="Frequently asked questions"
        subtitle="Quick answers to common questions about the platform."
      />
      <div className="space-y-4">
        {faqs.map((faq) => (
          <Card key={faq.question}>
            <CardHeader>
              <CardTitle className="text-base">{faq.question}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-6 text-muted-foreground">{faq.answer}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </PublicPage>
  );
}
