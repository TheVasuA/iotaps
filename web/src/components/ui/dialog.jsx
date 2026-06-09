import * as React from "react";
import { X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

// Lightweight modal dialog primitive (no Radix dependency). Renders an overlay
// + centered panel when `open`, traps Escape to close, and locks page scroll.
// Styling is bound to the CSS-variable palette so the active role theme
// (Req 4.1-4.3) colours it automatically.
export function Dialog({ open, onClose, children, className, title, description }) {
  React.useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={cn(
          "relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col rounded-lg border border-border bg-card text-card-foreground shadow-lg",
          className
        )}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <X size={16} />
        </button>
        {(title || description) && (
          <div className="shrink-0 space-y-1 border-b border-border p-6">
            {title ? (
              <h2 className="text-lg font-semibold leading-none tracking-tight">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}

export function DialogBody({ className, ...props }) {
  return <div className={cn("p-6", className)} {...props} />;
}

export function DialogFooter({ className, ...props }) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 border-t border-border p-6 pt-4",
        className
      )}
      {...props}
    />
  );
}
