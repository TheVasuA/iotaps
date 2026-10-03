import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Blynk-style auth text field — fixed height, 14px text/placeholder, vertically centered.
 */
const AuthInput = React.forwardRef(({ className, type = "text", ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "auth-input-field",
      type === "password" && "auth-input-password",
      className
    )}
    {...props}
  />
));
AuthInput.displayName = "AuthInput";

export default AuthInput;
