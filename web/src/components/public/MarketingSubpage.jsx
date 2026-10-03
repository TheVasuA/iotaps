import { Link } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { buildSrcSet, marketingImageSizes } from "@/lib/marketingImages";
import { buttonVariants } from "@/components/ui/button";
// From BlynkTypography, not BlynkMarketing: that module imports LandingReveal
// (framer-motion), and every marketing subpage would then pay for the
// vendor-motion chunk just to render an eyebrow and a heading.
import { BlynkEyebrow, BlynkSectionTitle } from "@/components/public/blynk/BlynkTypography";
import { usePageMeta } from "@/lib/usePageMeta";

/**
 * Marketing photo. `src` is either a bare URL or an enriched entry from
 * lib/marketingImages.js; intrinsic width/height reserve layout space (no CLS)
 * and the AVIF/WebP <source>s skip the heavier JPEG for modern browsers.
 * Each variant list becomes a multi-candidate `NNNw` srcset so narrow viewports
 * fetch the 800px tier instead of the full-width rendition; `sizes` (see
 * marketingImageSizes) tells the browser how wide the slot actually renders.
 */
export function MarketingImage({ src, alt, className, priority, sizes = marketingImageSizes }) {
  const image = typeof src === "string" ? { src } : src;
  const { src: fallback, width, height, sources } = image ?? {};
  const avifSrcSet = buildSrcSet(sources?.avif);
  const webpSrcSet = buildSrcSet(sources?.webp);
  const jpegSrcSet = buildSrcSet(sources?.jpg);
  return (
    /* display:contents so callers' sizing/positioning classes on <img> resolve
       against the same box they did before <picture> was introduced. */
    <picture className="contents">
      {avifSrcSet ? <source type="image/avif" srcSet={avifSrcSet} sizes={sizes} /> : null}
      {webpSrcSet ? <source type="image/webp" srcSet={webpSrcSet} sizes={sizes} /> : null}
      <img
        src={fallback}
        srcSet={jpegSrcSet}
        sizes={jpegSrcSet ? sizes : undefined}
        alt={alt}
        width={width}
        height={height}
        loading={priority ? "eager" : "lazy"}
        // LCP heroes need the browser to rank the image above the rest of the
        // preload queue. Lowercase on purpose: React 18.3 does not know the
        // camelCase `fetchPriority` DOM prop and warns on it — the lowercase
        // form passes through as the real HTML attribute.
        fetchpriority={priority ? "high" : undefined}
        decoding={priority ? "sync" : "async"}
        className={cn("h-full w-full object-cover", className)}
      />
    </picture>
  );
}

/** Top band for all public marketing / legal pages (matches landing visual system). */
export function MarketingPageHero({
  eyebrow,
  title,
  subtitle,
  image,
  imageAlt = "",
  imagePosition = "right",
}) {
  const hasImage = Boolean(image);

  return (
    <section
      className={cn(
        "relative overflow-hidden border-b border-white/10",
        hasImage ? "blynk-subpage-hero-split" : "blynk-subpage-hero"
      )}
    >
      <div
        className={cn(
          "mx-auto max-w-7xl px-6 py-14 sm:py-18 lg:py-20",
          hasImage && "grid items-center gap-10 lg:grid-cols-2 lg:gap-14"
        )}
      >
        <div className={cn(hasImage && imagePosition === "left" && "lg:order-2")}>
          {eyebrow ? <BlynkEyebrow className={hasImage ? "text-primary" : ""}>{eyebrow}</BlynkEyebrow> : null}
          <BlynkSectionTitle
            as="h1"
            dark={hasImage}
            className={cn("mt-3", !hasImage && "text-foreground")}
          >
            {title}
          </BlynkSectionTitle>
          {subtitle ? (
            <p
              className={cn(
                "mt-4 max-w-xl text-pretty text-base leading-relaxed sm:text-lg",
                hasImage ? "text-white/65" : "text-muted-foreground"
              )}
            >
              {subtitle}
            </p>
          ) : null}
        </div>
        {hasImage ? (
          <div
            className={cn(
              "marketing-hero-image-wrap overflow-hidden rounded-xl border border-white/10 shadow-2xl",
              imagePosition === "left" && "lg:order-1"
            )}
          >
            <MarketingImage src={image} alt={imageAlt} className="aspect-[4/3] min-h-[220px]" priority />
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function MarketingBody({ children, className, wide = false }) {
  return (
    <section className={cn("landing-section !py-12 sm:!py-16 lg:!py-20", className)}>
      <div className={cn("mx-auto px-6", wide ? "max-w-6xl" : "max-w-4xl")}>{children}</div>
    </section>
  );
}

export function MarketingPageHeader({ title, subtitle, as = "h2" }) {
  const Tag = as;
  return (
    <header className="mb-10 border-b border-border pb-8">
      <Tag className="font-brand text-2xl font-bold uppercase tracking-tight text-foreground sm:text-3xl">
        {title}
      </Tag>
      {subtitle ? (
        <p className="mt-3 max-w-2xl text-pretty text-base leading-relaxed text-muted-foreground">
          {subtitle}
        </p>
      ) : null}
    </header>
  );
}

export function MarketingProse({ sections }) {
  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <article key={section.heading} className="blynk-platform-card p-6 sm:p-8">
          {/* h2: sits directly under the page hero's h1, so h3 would skip a level. */}
          <h2 className="text-lg font-bold uppercase tracking-wide text-foreground">
            {section.heading}
          </h2>
          <div className="mt-4 space-y-3">
            {section.body.map((paragraph, idx) => (
              <p key={idx} className="text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
                {paragraph}
              </p>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

export function MarketingBottomCta() {
  return (
    <section className="border-t border-border bg-[#fafafa] py-14 dark:bg-muted/20">
      <div className="mx-auto flex max-w-4xl flex-col items-center px-6 text-center">
        <BlynkEyebrow>Get started</BlynkEyebrow>
        <p className="mt-3 font-brand text-xl font-bold uppercase tracking-tight sm:text-2xl">
          Ready to connect your first device?
        </p>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Free tier · No credit card · Console included
        </p>
        <Link to="/register" className={cn(buttonVariants({ size: "lg" }), "mt-6")}>
          Sign up free
          <ArrowRight size={18} weight="bold" />
        </Link>
      </div>
    </section>
  );
}

/** Full wrapper: hero + body + bottom CTA */
export function MarketingShell({
  eyebrow,
  title,
  subtitle,
  image,
  imageAlt,
  imagePosition,
  wide,
  children,
  showCta = true,
  // SEO overrides. When omitted we fall back to the visible title / subtitle so
  // every page still gets a distinct document title and meta description.
  metaTitle,
  metaDescription,
  metaImage,
  noindex,
}) {
  usePageMeta({
    title: metaTitle || title,
    description: metaDescription || subtitle,
    image: metaImage,
    noindex,
  });

  return (
    <>
      <MarketingPageHero
        eyebrow={eyebrow}
        title={title}
        subtitle={subtitle}
        image={image}
        imageAlt={imageAlt}
        imagePosition={imagePosition}
      />
      <MarketingBody wide={wide}>{children}</MarketingBody>
      {showCta ? <MarketingBottomCta /> : null}
    </>
  );
}
