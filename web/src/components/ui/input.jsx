import * as React from "react";
import { cn } from "@/lib/utils";

const inputStyles = {
  default:
    "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
  underline:
    "h-auto rounded-none border-0 border-transparent bg-transparent px-0 py-2.5 text-sm shadow-none ring-offset-0 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-50",
  auth:
    "auth-input h-12 rounded-none border border-zinc-200 bg-white px-3 py-0 text-base leading-normal text-zinc-900 shadow-none ring-offset-0 placeholder:text-base placeholder:leading-normal placeholder:text-zinc-400 focus-visible:border-zinc-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-300 disabled:cursor-not-allowed disabled:opacity-50",
};

// shadcn/ui-style text input bound to the CSS-variable palette.
const Input = React.forwardRef(({ className, type = "text", variant = "default", ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(inputStyles[variant] ?? inputStyles.default, className)}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
