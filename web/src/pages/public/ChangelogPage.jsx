import { useEffect, useState } from "react";
import { CircleNotch } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PublicPage, PageHeader } from "@/components/public/PublicPage";
import { getPublicChangelog } from "@/lib/publicApi";

// Public Changelog page (Task 21.1, Req 31.1). Lists published changelog
// entries (newest first) from GET /changelog. Anonymous visitors who cannot
// load the feed see a graceful empty state rather than an error screen.

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

  useEffect(() => {
    let cancelled = false;
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
  }, []);

  return (
    <PublicPage>
      <PageHeader
        title="Changelog"
        subtitle="What's new on the IoTAPS platform."
      />

      {state === "loading" ? (
        <div className="flex justify-center py-16 text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : state === "error" || entries.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">No updates yet</CardTitle>
            <CardDescription>
              Published updates will appear here. Check back soon.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-6">
          {entries.map((entry) => {
            const date = formatDate(entry.published_at);
            return (
              <Card key={entry.id}>
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-3">
                    {entry.version ? (
                      <Badge variant="outline">{entry.version}</Badge>
                    ) : null}
                    <CardTitle className="text-lg">
                      {entry.title || "Update"}
                    </CardTitle>
                    {date ? (
                      <span className="text-xs text-muted-foreground">{date}</span>
                    ) : null}
                  </div>
                </CardHeader>
                {entry.body ? (
                  <CardContent>
                    <p className="whitespace-pre-line text-sm leading-6 text-muted-foreground">
                      {entry.body}
                    </p>
                  </CardContent>
                ) : null}
              </Card>
            );
          })}
        </div>
      )}
    </PublicPage>
  );
}
