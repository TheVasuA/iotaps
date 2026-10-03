import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle } from "@phosphor-icons/react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function badgeClass(variant) {
  if (variant === "enterprise") return "wl-feature-badge wl-feature-badge-enterprise";
  if (variant === "company") return "wl-feature-badge wl-feature-badge-company";
  if (variant === "pro") return "wl-feature-badge wl-feature-badge-pro";
  return "wl-feature-badge wl-feature-badge-soon";
}

export default function ConsoleFeatureScreen({
  title,
  eyebrow,
  description,
  bullets = [],
  badge,
  badgeVariant = "soon",
  icon: Icon,
  primaryCta,
  secondaryCta,
}) {
  return (
    <div className="wl-feature-screen">
      <div className="wl-feature-screen-bg" aria-hidden />
      <div className="wl-feature-screen-inner">
        <div className="wl-feature-copy">
          <span className={badgeClass(badgeVariant)}>{badge}</span>
          <p className="wl-feature-eyebrow">{eyebrow}</p>
          <h1 className="wl-feature-title">{title}</h1>
          <p className="wl-feature-description">{description}</p>
          <ul className="wl-feature-list">
            {bullets.map((line) => (
              <li key={line}>
                <CheckCircle size={18} weight="fill" className="shrink-0 text-primary" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          <div className="wl-feature-actions">
            {primaryCta ? (
              <Link to={primaryCta.to} className={cn(buttonVariants(), "font-semibold shadow-sm")}>
                {primaryCta.label}
                <ArrowRight size={16} className="ml-2" weight="bold" />
              </Link>
            ) : null}
            {secondaryCta ? (
              <Link
                to={secondaryCta.to}
                className={cn(buttonVariants({ variant: "outline" }), "font-semibold")}
              >
                {secondaryCta.label}
              </Link>
            ) : null}
          </div>
        </div>

        <div className="wl-feature-visual" aria-hidden>
          <div className="wl-feature-visual-card">
            <div className="wl-feature-visual-icon">
              <Icon size={48} weight="duotone" />
            </div>
            <div className="wl-feature-visual-lines">
              <span />
              <span />
              <span className="wl-feature-visual-lines-short" />
            </div>
            <div className="wl-feature-visual-grid">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="wl-feature-visual-cell" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
