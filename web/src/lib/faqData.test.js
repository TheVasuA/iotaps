// Guards for the shared FAQ content and its schema.org serialization.
//
// The same module feeds both the React FAQ page and the build-time prerender
// (scripts/prerender.mjs runs under bare Node and cannot import JSX), so a
// shape change here breaks two consumers at once. The JSON-LD serializer is
// also the only thing standing between page copy and an early `</script>`
// termination, so its escaping is pinned explicitly.

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  faqs,
  buildFaqJsonLd,
  toJsonLdScriptText,
  faqJsonLdScriptText,
} from "./faqData.js";
import { SITE_ROUTES } from "./siteRoutes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const generateSeoSource = readFileSync(
  join(__dirname, "../../scripts/generate-seo.mjs"),
  "utf8"
);
const prerenderSource = readFileSync(
  join(__dirname, "../../scripts/prerender.mjs"),
  "utf8"
);
const packageJson = JSON.parse(
  readFileSync(join(__dirname, "../../package.json"), "utf8")
);

describe("faqData", () => {
  it("has at least one entry of non-empty question/answer strings", () => {
    expect(faqs.length).toBeGreaterThan(0);
    for (const faq of faqs) {
      expect(typeof faq.question).toBe("string");
      expect(faq.question.trim().length).toBeGreaterThan(0);
      expect(typeof faq.answer).toBe("string");
      expect(faq.answer.trim().length).toBeGreaterThan(0);
    }
  });

  it("has unique questions", () => {
    const questions = faqs.map((faq) => faq.question);
    expect(new Set(questions).size).toBe(questions.length);
  });
});

describe("buildFaqJsonLd", () => {
  const jsonLd = buildFaqJsonLd();

  it("is a schema.org FAQPage", () => {
    expect(jsonLd["@context"]).toBe("https://schema.org");
    expect(jsonLd["@type"]).toBe("FAQPage");
  });

  it("wraps every entry as a Question with an acceptedAnswer", () => {
    expect(Array.isArray(jsonLd.mainEntity)).toBe(true);
    expect(jsonLd.mainEntity).toHaveLength(faqs.length);
    for (let i = 0; i < faqs.length; i += 1) {
      const entity = jsonLd.mainEntity[i];
      expect(entity["@type"]).toBe("Question");
      expect(entity.name).toBe(faqs[i].question);
      expect(entity.acceptedAnswer["@type"]).toBe("Answer");
      expect(entity.acceptedAnswer.text).toBe(faqs[i].answer);
    }
  });
});

describe("toJsonLdScriptText", () => {
  it("escapes </script sequences so the block cannot terminate early", () => {
    const hostile = {
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "</script><script>alert(1)</script>",
          acceptedAnswer: { "@type": "Answer", text: "</script>" },
        },
      ],
    };
    const text = toJsonLdScriptText(hostile);
    expect(/<\/script/i.test(text)).toBe(false);
    expect(text).toContain("\\u003c/script");
    // Escaping is JSON-safe: consumers still decode the original text.
    expect(JSON.parse(text)).toEqual(hostile);
  });

  it("serializes the real FAQ payload losslessly", () => {
    expect(JSON.parse(faqJsonLdScriptText())).toEqual(buildFaqJsonLd());
  });
});

describe("prerender wiring", () => {
  // A full prerender (scripts/prerender.mjs) is what no-JS crawlers actually
  // read now: complete, styled page HTML written at the route path itself,
  // SPA scripts included. The FAQ JSON-LD has to ride along with that page,
  // and generate-seo must stop emitting the unstyled side-channel snapshot
  // this replaces.
  it("writes FAQ HTML at the /faq route path from the SITE_ROUTES enumeration", () => {
    // The route list is enumerated at runtime, so a route added to siteRoutes
    // is prerendered without editing the script.
    expect(prerenderSource).toContain("SITE_ROUTES");
    // …and each route lands at <path>/index.html, not at a side-channel name.
    expect(prerenderSource).toMatch(/outputPathsFor\(/);
    expect(SITE_ROUTES.map((route) => route.path)).toContain("/faq");
  });

  it("carries the shared FAQ JSON-LD into the prerendered page", () => {
    expect(prerenderSource).toContain("faqData.js");
    expect(prerenderSource).toMatch(/application\/ld\+json/);
  });

  it("no longer emits the unstyled faq.html side-channel", () => {
    // The side-channel existed only because a styled page could not sit at
    // /faq without shadowing the SPA. The prerendered page is a drop-in
    // replacement, so the snapshot must be gone entirely.
    expect(generateSeoSource).not.toContain("faq.html");
    expect(generateSeoSource).not.toMatch(/buildFaqHtml/);
    expect(generateSeoSource).not.toMatch(/rmSync\(join\(targetDir,\s*["'`]faq["'`]\)/);
  });

  it("orders the build so prerender writes last and nothing clobbers route HTML", () => {
    // generate-seo used to rmSync dist/faq as a shadowing guard — safe when it
    // ran alone, but a no-op for prerender if it ever ran afterwards. Pin the
    // order in package.json: the SEO step must not be able to delete route
    // directories after prerender has written them.
    const build = packageJson.scripts.build;
    const viteAt = build.indexOf("vite build");
    const seoAt = build.indexOf("generate-seo");
    const prerenderAt = build.indexOf("prerender");
    expect(viteAt).toBeGreaterThanOrEqual(0);
    expect(seoAt).toBeGreaterThan(viteAt);
    expect(prerenderAt).toBeGreaterThan(seoAt);
  });
});
