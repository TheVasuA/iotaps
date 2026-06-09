import { CircleNotch } from "@phosphor-icons/react";

// Shared loading/error/empty frame for Super_Admin panels (Task 20.7).
// Centralizes the loading spinner and error surface so every admin panel
// behaves consistently. `status` is one of "loading" | "succeeded" | "failed".
export default function AdminPanel({ status, error, children, emptyFallback }) {
  if (status === "loading") {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <CircleNotch size={24} className="animate-spin" />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-destructive">
        {error || "Failed to load data"}
      </div>
    );
  }
  return children ?? emptyFallback ?? null;
}
