import { cn } from "@/lib/utils";

// IoTAPS logo — matches favicon.svg. Uses CSS currentColor for the background
// so it adapts to the theme's primary color.
export default function Logo({ size = 24, className }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={cn("shrink-0", className)}
    >
      <rect width="32" height="32" rx="7" className="fill-primary" />
      <circle cx="16" cy="16" r="4" fill="#fff" />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="#fff" strokeWidth="1.6" opacity="0.7" />
      <circle cx="16" cy="16" r="12.5" fill="none" stroke="#fff" strokeWidth="1.2" opacity="0.4" />
    </svg>
  );
}
