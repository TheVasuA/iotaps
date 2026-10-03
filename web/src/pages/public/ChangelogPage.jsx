import { useEffect, useState } from "react";
import { CircleNotch } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { MarketingShell, MarketingPageHeader } from "@/components/public/PublicPage";
import { marketingImages } from "@/lib/marketingImages";
import { getPublicChangelog } from "@/lib/publicApi";
import { cn } from "@/lib/utils";

// Public Changelog page (Task 21.1, Req 31.1). Lists published changelog
// entries (newest first) from GET /changelog. A failed fetch is shown as its
// own error state with a Retry action, distinct from a genuinely empty feed,
// so a real outage is never disguised as "No updates yet".

function formatDate(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function ChangelogPage() {
  const [entries, setEntries] = useState([]);
  const [state, setState] = useState("loading"); // loading | ready | error
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    (async () => {
      try {
        const data = await getPublicChangelog();
        if (!cancelled) {
          setEntries(Array.isArray(data) ? data : []);
          setState("ready");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // Re-run the fetch from the error card (back to loading first).
  const retry = () => setReloadKey((key) => key + 1);

  return (
    <MarketingShell
      eyebrow="Product"
      title="Changelog"
      subtitle="What's new on the IoTAPS platform."
      image={marketingImages.consoleDesk}
      imageAlt="Product updates and platform improvements"
    >
      <MarketingPageHeader title="Release history" subtitle="Published updates appear below, newest first." />

      {state === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : state === "error" ? (
        <article className="blynk-platform-card p-6">
          <h3 className="text-lg font-bold">Could not load updates</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Something went wrong while loading the changelog. Please try again.
          </p>
          <button
            type="button"
            onClick={retry}
            className={cn(buttonVariants({ variant: "outline" }), "mt-4")}
          >
            Retry
          </button>
        </article>
      ) : entries.length === 0 ? (
        <article className="blynk-platform-card p-6">
          <h3 className="text-lg font-bold">No updates yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Published updates will appear here. Check back soon.
          </p>
        </article>
      ) : (
        <div className="space-y-4">
          {entries.map((entry) => {
            const date = formatDate(entry.published_at);
            return (
              <article key={entry.id} className="blynk-platform-card p-6 sm:p-7">
                <div className="flex flex-wrap items-center gap-3">
                  {entry.version ? <Badge variant="outline">{entry.version}</Badge> : null}
                  <h3 className="text-lg font-bold">{entry.title || "Update"}</h3>
                  {date ? <span className="text-xs text-muted-foreground">{date}</span> : null}
                </div>
                {entry.body ? (
                  <p className="mt-4 whitespace-pre-line text-sm leading-7 text-muted-foreground">
                    {entry.body}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </MarketingShell>
  );
}
