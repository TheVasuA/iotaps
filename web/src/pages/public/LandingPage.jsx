import {
  LandingHero,
  LogoMarquee,
  SolutionsGallery,
  PlatformExplore,
  FeaturedInsights,
  ComplexityGrid,
  TestimonialSection,
  AppShowcaseStrip,
  InfrastructureSection,
  BigStatementSection,
  LandingFinalCta,
} from "@/components/public/blynk/BlynkMarketing";
import { usePageMeta } from "@/lib/usePageMeta";

export default function LandingPage() {
  usePageMeta({
    title: "IoTAPS — IoT Automation Platform Services",
    description:
      "Ship connected hardware with one console for fleet, data and apps. MQTT-native provisioning, live dashboards, rule chains, and billing — without rebuilding cloud infrastructure.",
  });

  return (
    <>
      <LandingHero />
      <LogoMarquee />
      <SolutionsGallery />
      <PlatformExplore />
      <FeaturedInsights />
      <ComplexityGrid />
      <TestimonialSection />
      <AppShowcaseStrip />
      <InfrastructureSection />
      <BigStatementSection />
      <LandingFinalCta />
    </>
  );
}
