import { cn } from "@/lib/utils";
import AuthInput from "@/components/auth/AuthInput";

export const authLinkClass =
  "font-medium text-[#2563eb] underline-offset-2 hover:underline dark:text-sky-400";

export function AuthDivider({ label = "or" }) {
  return (
    <div className="relative py-1">
      <div className="absolute inset-0 flex items-center">
        <div className="w-full border-t border-zinc-200" />
      </div>
      <div className="relative flex justify-center">
        <span className="auth-card bg-white px-3 text-xs uppercase tracking-wide text-zinc-400">
          {label}
        </span>
      </div>
    </div>
  );
}

export function AuthField({ id, label, icon: Icon, className, inputClassName, ...inputProps }) {
  return (
    <div className={cn("space-y-2", className)}>
      <label htmlFor={id} className="auth-label">
        {label}
      </label>
      <div className="relative h-11">
        {Icon ? (
          <Icon
            size={18}
            className="pointer-events-none absolute left-3 top-1/2 z-10 -translate-y-1/2 text-zinc-400"
            aria-hidden
          />
        ) : null}
        <AuthInput
          id={id}
          className={cn(Icon && "auth-input-with-icon", inputClassName)}
          {...inputProps}
        />
      </div>
    </div>
  );
}
