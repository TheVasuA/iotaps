import { useEffect } from "react";
import { MarketingShell, MarketingPageHeader } from "@/components/public/PublicPage";
import { marketingImages } from "@/lib/marketingImages";
import { faqs, faqJsonLdScriptText } from "@/lib/faqData";

// Id for the FAQ JSON-LD block. Client-side navigation mounts this page more
// than once per document, so the effect keys on this id instead of appending
// an unbounded stack of <script> tags.
const FAQ_JSON_LD_ID = "iotaps-faq-jsonld";

export default function FaqPage() {
  // FAQPage structured data. Crawlers that do not run JS get the same payload
  // from the static page scripts/generate-seo.mjs writes to dist/faq/index.html.
  useEffect(() => {
    let el = document.head.querySelector(`script[type="application/ld+json"]#${FAQ_JSON_LD_ID}`);
    const created = !el;
    const previousText = el ? el.textContent : null;
    if (created) {
      el = document.createElement("script");
      el.type = "application/ld+json";
      el.id = FAQ_JSON_LD_ID;
      document.head.appendChild(el);
    }
    el.textContent = faqJsonLdScriptText();

    // Undo on unmount so navigating to a non-FAQ route does not leave the
    // previous page's structured data behind (same discipline as usePageMeta).
    return () => {
      if (created) el.remove();
      else el.textContent = previousText;
    };
  }, []);

  return (
    <MarketingShell
      eyebrow="Support"
      title="Frequently asked questions"
      subtitle="Quick answers to common questions about the platform."
      image={marketingImages.solutionsAgriculture}
      imageAlt="IoT sensors in a greenhouse environment"
    >
      <MarketingPageHeader title="Common topics" subtitle="Can't find what you need? Contact us or open in-app support." />
      <div className="space-y-3">
        {faqs.map((faq) => (
          <article key={faq.question} className="blynk-platform-card p-6 sm:p-7">
            <h3 className="text-base font-bold leading-snug">{faq.question}</h3>
            <p className="mt-3 text-pretty text-sm leading-7 text-muted-foreground">{faq.answer}</p>
          </article>
        ))}
      </div>
    </MarketingShell>
  );
}
