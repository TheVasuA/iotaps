import { Link } from "react-router-dom";
import { ArrowLeft, Compass, Question } from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { MarketingPageHero, MarketingBody } from "@/components/public/MarketingSubpage";
import { MarketingRelatedLinks } from "@/pages/public/marketing/createMarketingPage";
import { usePageMeta } from "@/lib/usePageMeta";
import { cn } from "@/lib/utils";

/**
 * 404 for the public marketing surface. Rendered inside PublicLayout so a
 * mistyped URL still has the header, footer, and a way forward — the previous
 * catch-all was a bare unstyled div with no navigation out.
 */
export default function NotFoundPage() {
  usePageMeta({
    title: "Page not found",
    description: "The page you were looking for does not exist on iotaps.com.",
    noindex: true,
  });

  return (
    <>
      <MarketingPageHero
        eyebrow="404"
        title="Page not found"
        subtitle="We couldn't find that page. It may have moved, or the link may be out of date."
      />
      <MarketingBody>
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <Link to="/" className={cn(buttonVariants({ size: "lg" }), "w-full sm:w-auto")}>
            <ArrowLeft size={18} weight="bold" aria-hidden />
            Back to home
          </Link>
          <Link
            to="/contact"
            className={cn(
              buttonVariants({ variant: "outline", size: "lg" }),
              "w-full sm:w-auto"
            )}
          >
            <Question size={18} weight="bold" aria-hidden />
            Contact support
          </Link>
        </div>

        <MarketingRelatedLinks
          title="Popular pages"
          links={[
            { to: "/", label: "Home" },
            { to: "/platform", label: "Platform" },
            { to: "/pricing", label: "Pricing" },
            { to: "/docs", label: "Docs" },
            { to: "/faq", label: "FAQ" },
            { to: "/status", label: "System status" },
          ]}
        />

        <p className="mt-6 flex items-start gap-2 text-sm text-muted-foreground">
          <Compass size={18} className="mt-0.5 shrink-0 text-primary" aria-hidden />
          <span>
            Looking for developer docs? Start at{" "}
            <Link to="/developers" className="font-semibold text-primary hover:underline">
              Developers
            </Link>{" "}
            or jump straight to{" "}
            <Link to="/developers/mqtt-devices" className="font-semibold text-primary hover:underline">
              MQTT &amp; devices
            </Link>
            .
          </span>
        </p>
      </MarketingBody>
    </>
  );
}
