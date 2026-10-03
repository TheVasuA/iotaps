import { cn } from "@/lib/utils";

/** Inner white card shared by AuthShell and in-app security flows. */
export default function AuthCard({ title, subtitle, children, footer, className }) {
  return (
    <div
      className={cn(
        "auth-card w-full max-w-[420px] px-8 py-9 sm:px-10 sm:py-10",
        className
      )}
    >
      <h1 className="text-center text-xl font-bold tracking-tight text-zinc-900">{title}</h1>
      {subtitle ? (
        <p className="mt-2 text-center text-sm leading-relaxed text-zinc-500">{subtitle}</p>
      ) : null}
      <div className={cn(subtitle ? "mt-6" : "mt-7")}>{children}</div>
      {footer ? (
        <p className="auth-card-footer mt-8 border-t border-zinc-200 pt-6 text-center text-sm text-zinc-500">
          {footer}
        </p>
      ) : null}
    </div>
  );
}
