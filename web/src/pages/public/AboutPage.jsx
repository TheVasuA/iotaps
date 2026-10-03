import { MarketingShell, MarketingProse } from "@/components/public/PublicPage";
import { MarketingRelatedLinks } from "@/pages/public/marketing/createMarketingPage";
import { marketingImages } from "@/lib/marketingImages";

const sections = [
  {
    heading: "Our mission",
    body: [
      "IoTAPS makes it simple for organizations to provision IoT devices, visualize their data, and automate their behavior — without stitching together a dozen tools.",
      "We focus on the Indian market with familiar payment methods, volume pricing, and a partner program that rewards the businesses growing the platform with us.",
    ],
  },
  {
    heading: "What we build",
    body: [
      "A multi-tenant platform spanning device management, a real-time telemetry pipeline, drag-and-drop dashboards, remote control, a visual rule engine, and subscription billing.",
      "Everything is designed to run efficiently on a single node today while staying ready to scale to tens of thousands of devices.",
    ],
  },
  {
    heading: "Who it's for",
    body: [
      "Project centers managing device fleets, students learning IoT with ready-made templates, and end customers who simply want to view and control their devices.",
    ],
  },
];

export default function AboutPage() {
  return (
    <MarketingShell
      eyebrow="Company"
      title="About IoTAPS"
      subtitle="The platform behind connected device fleets — built for teams who ship hardware, not cloud plumbing."
      image={marketingImages.heroFleet}
      imageAlt="Industrial IoT deployment in a modern facility"
    >
      <MarketingRelatedLinks
        links={[
          { to: "/partners", label: "Partners" },
          { to: "/blog", label: "Product updates" },
          { to: "/case-studies", label: "Deployment patterns" },
          { to: "/contact", label: "Contact" },
        ]}
      />
      <MarketingProse sections={sections} />
    </MarketingShell>
  );
}
