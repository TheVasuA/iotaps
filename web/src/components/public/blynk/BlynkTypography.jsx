import { cn } from "@/lib/utils";

/**
 * Static brand typography shared by the landing page and every marketing
 * subpage.
 *
 * These two live apart from BlynkMarketing.jsx on purpose: that module imports
 * LandingReveal (framer-motion) for its scroll animations, and importing it
 * from MarketingSubpage dragged the ~115KB vendor-motion chunk onto every
 * plain content page (about, privacy, terms, faq, …) just to render an eyebrow
 * and a heading. Keep animation-only code out of this file.
 */

export function BlynkEyebrow({ children, className }) {
  return (
    <p
      className={cn(
        "landing-eyebrow text-[11px] font-semibold uppercase tracking-[0.28em] text-primary",
        className
      )}
    >
      {children}
    </p>
  );
}

export function BlynkSectionTitle({ as: Tag = "h2", children, className, dark, balanced = true }) {
  return (
    <Tag
      className={cn(
        "font-brand text-[clamp(1.5rem,2.5vw+0.75rem,2.75rem)] font-bold uppercase leading-[1.08] tracking-tight",
        balanced && "text-balance",
        dark ? "text-white" : "text-foreground",
        className
      )}
    >
      {children}
    </Tag>
  );
}
