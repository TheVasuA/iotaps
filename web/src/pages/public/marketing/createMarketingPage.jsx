import { Link } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { MarketingShell, MarketingProse } from "@/components/public/PublicPage";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

export function MarketingRelatedLinks({ links, title = "Related" }) {
  if (!links?.length) return null;
  return (
    <nav className="mb-10 rounded-xl border border-border bg-muted/30 p-5" aria-label={title}>
      <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{title}</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {links.map((item) => (
          <li key={item.to + item.label}>
            <Link
              to={item.to}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground transition hover:border-primary/40 hover:text-primary"
            >
              {item.label}
              <ArrowRight size={12} weight="bold" />
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function createMarketingPage({ shell, sections, relatedLinks, children }) {
  return function MarketingPage() {
    return (
      <MarketingShell {...shell}>
        <MarketingRelatedLinks links={relatedLinks} />
        {sections?.length ? <MarketingProse sections={sections} /> : null}
        {typeof children === "function" ? children() : children}
      </MarketingShell>
    );
  };
}

export function MarketingCardGrid({ items }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="blynk-platform-card group flex flex-col p-6 transition hover:border-primary/30"
        >
          {item.eyebrow ? (
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary">{item.eyebrow}</span>
          ) : null}
          {/* h2: these cards are the page's content sections under the hero h1. */}
          <h2 className="mt-2 text-base font-bold uppercase tracking-tight group-hover:text-primary">
            {item.title}
          </h2>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
          <span className="mt-4 inline-flex items-center gap-1 text-xs font-bold uppercase text-primary">
            Learn more <ArrowRight size={14} weight="bold" />
          </span>
        </Link>
      ))}
    </div>
  );
}

export function MarketingBlogList({ posts }) {
  return (
    <ul className="space-y-4">
      {posts.map((post) => (
        <li key={post.to}>
          <Link to={post.to} className="blynk-platform-card block p-6 transition hover:border-primary/30 sm:p-8">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{post.date}</p>
            <h2 className="mt-2 text-lg font-bold tracking-tight text-foreground">{post.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{post.excerpt}</p>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-primary">
              Open <ArrowRight size={14} weight="bold" />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function MarketingCtaInline({ title, to, label }) {
  return (
    <div className="mt-8 rounded-xl border border-primary/20 bg-primary/5 p-6 text-center sm:p-8">
      <p className="font-brand text-lg font-bold uppercase tracking-tight">{title}</p>
      <Link to={to} className={cn(buttonVariants({ size: "lg" }), "mt-4 inline-flex")}>
        {label}
        <ArrowRight size={18} weight="bold" />
      </Link>
    </div>
  );
}
