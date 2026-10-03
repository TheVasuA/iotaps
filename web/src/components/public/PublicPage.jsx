// Shared layout primitives for public pages — re-exports marketing shell for
// consistency with the Blynk-style landing system.

export {
  MarketingShell,
  MarketingBody,
  MarketingPageHero,
  MarketingPageHeader,
  MarketingProse,
  MarketingBottomCta,
  MarketingImage,
} from "@/components/public/MarketingSubpage";

/** @deprecated Prefer MarketingBody + MarketingPageHeader */
export function PublicPage({ children, className = "" }) {
  return (
    <section className={`mx-auto max-w-4xl px-6 py-12 ${className}`.trim()}>{children}</section>
  );
}

/** @deprecated Prefer MarketingPageHeader inside MarketingShell */
export function PageHeader({ title, subtitle }) {
  return (
    <header className="mb-8 space-y-2 border-b border-border pb-6">
      <h1 className="text-3xl font-bold uppercase tracking-tight text-foreground">{title}</h1>
      {subtitle ? <p className="text-base text-muted-foreground">{subtitle}</p> : null}
    </header>
  );
}

/** @deprecated Prefer MarketingProse */
export function Prose({ sections }) {
  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <article key={section.heading} className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">{section.heading}</h2>
          {section.body.map((paragraph, idx) => (
            <p key={idx} className="text-sm leading-6 text-muted-foreground">
              {paragraph}
            </p>
          ))}
        </article>
      ))}
    </div>
  );
}
