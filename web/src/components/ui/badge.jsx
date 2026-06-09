import * as React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

// shadcn/ui-style status badge. Variants map to the CSS-variable palette so the
// active role theme colours them consistently.
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        success:
          "border-transparent bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
        muted:
          "border-transparent bg-muted text-muted-foreground",
        warning:
          "border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
