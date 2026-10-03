// Shared FAQ content for the public marketing surface.
//
// Lives as plain ESM (no JSX) so two very different consumers can import it:
// the React FAQ page, and scripts/generate-seo.mjs, which runs under bare Node
// at build time and cannot load a .jsx module. Keep it the single source of
// truth — edit the copy here and both the rendered page and the crawler-facing
// JSON-LD move together.

export const faqs = [
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

/**
 * schema.org FAQPage object for the shared questions.
 * https://developers.google.com/search/docs/appearance/structured-data/faqpage
 */
export function buildFaqJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
}

/**
 * Serialize JSON-LD so the result is safe to drop inside a <script> element.
 *
 * Every "<" is written as the JSON escape <, so a question or answer that
 * happens to contain "</script>" cannot terminate the block early — and HTML
 * comment openers can't start one either. JSON parsers decode < back to
 * "<", so consumers see the original text.
 */
export function toJsonLdScriptText(data) {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/** Ready-to-embed <script type="application/ld+json"> body for the FAQ page. */
export function faqJsonLdScriptText() {
  return toJsonLdScriptText(buildFaqJsonLd());
}
