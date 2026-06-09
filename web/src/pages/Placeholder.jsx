// Placeholder page used by the routing skeleton. Real screens replace these in
// their feature tasks (auth 2.8, dashboards 8.x, devices 4.5, admin 20.7, etc.).
export default function Placeholder({ title, note }) {
  return (
    <section className="mx-auto max-w-2xl space-y-3 rounded-lg border border-border bg-card p-8 text-card-foreground">
      <h1 className="text-2xl font-semibold text-primary">{title}</h1>
      <p className="text-sm text-muted-foreground">
        {note || "This screen is part of the routing skeleton and will be implemented in a later task."}
      </p>
    </section>
  );
}
