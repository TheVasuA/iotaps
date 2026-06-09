import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkle, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { getUnseenChangelog, markChangelogSeen } from "@/lib/changelogApi";

// "What's new" popup (Task 19.7, Req 22.2). On sign-in the SPA calls
// GET /changelog/unseen; when `show_popup` is true it animates in a popup with
// the entries published since the user's last view. Dismissing it calls
// POST /changelog/seen so it does not reappear for those entries.

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function WhatsNewPopup() {
  const [entries, setEntries] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { show_popup: showPopup, entries: unseen } =
          await getUnseenChangelog();
        if (!cancelled && showPopup && unseen?.length) {
          setEntries(unseen);
          setOpen(true);
        }
      } catch {
        // A failed unseen check must never block the app; just skip the popup.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = async () => {
    setOpen(false);
    try {
      // Mark seen so the popup does not reappear for these entries (Req 22.2).
      await markChangelogSeen();
    } catch {
      /* best-effort; the popup is already dismissed for this session */
    }
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-label="What's new"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div
            className="absolute inset-0 bg-black/50"
            onClick={dismiss}
            aria-hidden="true"
          />
          <motion.div
            className="relative z-10 w-full max-w-lg overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-lg"
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 300, damping: 26 }}
          >
            <button
              type="button"
              onClick={dismiss}
              aria-label="Close"
              className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <X size={16} />
            </button>

            <div className="flex items-center gap-2 border-b border-border p-6">
              <Sparkle size={22} weight="fill" className="text-primary" />
              <h2 className="text-lg font-semibold leading-none tracking-tight">
                What&apos;s new
              </h2>
            </div>

            <div className="max-h-[60vh] space-y-5 overflow-y-auto p-6">
              {entries.map((entry, idx) => {
                const published = formatDate(entry.published_at);
                return (
                  <motion.article
                    key={entry.id}
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.05 * idx, duration: 0.2 }}
                    className="space-y-1"
                  >
                    <div className="flex items-baseline gap-2">
                      <h3 className="font-medium text-foreground">
                        {entry.title || "Update"}
                      </h3>
                      {entry.version ? (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                          {entry.version}
                        </span>
                      ) : null}
                    </div>
                    {entry.body ? (
                      <p className="whitespace-pre-line text-sm text-muted-foreground">
                        {entry.body}
                      </p>
                    ) : null}
                    {published ? (
                      <p className="text-xs text-muted-foreground">{published}</p>
                    ) : null}
                  </motion.article>
                );
              })}
            </div>

            <div className="flex items-center justify-end border-t border-border p-6 pt-4">
              <Button type="button" onClick={dismiss}>
                Got it
              </Button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
