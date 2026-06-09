// Shared layout primitives for the public informational pages (Task 21.1).
// Keeps the marketing/legal pages visually consistent without repeating the
// container + heading boilerplate on every page.

export function PublicPage({ children, className = "" }) {
  return (
    <section className={`mx-auto max-w-4xl px-6 py-12 ${className}`.trim()}>
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle }) {
  return (
    <header className="mb-8 space-y-2">
      <h1 className="text-3xl font-bold tracking-tight text-primary">{title}</h1>
      {subtitle ? (
        <p className="text-base text-muted-foreground">{subtitle}</p>
      ) : null}
    </header>
  );
}

// Renders a list of { heading, body } sections as readable prose, used by the
// Terms, Privacy, and Refund Policy pages.
export function Prose({ sections }) {
  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <article key={section.heading} className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">
            {section.heading}
          </h2>
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
