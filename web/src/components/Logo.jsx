import { useId } from "react";
import { cn } from "@/lib/utils";

// IoTAPS logo — energy bolt in a glossy purple core, wrapped by a tilted orbit
// ring with a sparkle star at its end. Matches favicon.svg.
// Gradient IDs are unique per instance so multiple logos can share a page.
export default function Logo({ size = 24, className }) {
  const uid = useId().replace(/[:]/g, "");
  const sphere = `sphere-${uid}`;
  const ring = `ring-${uid}`;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="10 12 44 40"
      width={Math.round(size * 1.1)}
      height={size}
      role="img"
      aria-label="IoTAPS"
      className={cn("shrink-0", className)}
    >
      <defs>
        <linearGradient id={sphere} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#9b6bff" />
          <stop offset="100%" stopColor="#6d28d9" />
        </linearGradient>
        <linearGradient id={ring} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="50%" stopColor="#e9d5ff" />
          <stop offset="100%" stopColor="#7c3aed" />
        </linearGradient>
      </defs>

      {/* ring BACK half */}
      <g transform="translate(32,32) rotate(-24)">
        <path d="M -22 0 A 22 6.6 0 0 1 22 0" fill="none" stroke="#7c3aed" strokeWidth="1.4" strokeLinecap="round" opacity="0.45" />
      </g>

      {/* core sphere */}
      <circle cx="32" cy="32" r="11.5" fill={`url(#${sphere})`} />

      {/* energy bolt */}
      <path d="M 34 25 L 28.2 33.2 L 31.6 33.2 L 30 39 L 36 30.4 L 32.4 30.4 Z" fill="#ffffff" />

      {/* ring FRONT half + sparkle star */}
      <g transform="translate(32,32) rotate(-24)">
        <path d="M 22 0 A 22 6.6 0 0 1 -22 0" fill="none" stroke={`url(#${ring})`} strokeWidth="2.2" strokeLinecap="round" />
        <g transform="translate(22,0)">
          <circle r="1.9" fill="#c9a8ff" opacity="0.3" />
          <path d="M 0 -2.2 L 0.6 -0.6 L 2.2 0 L 0.6 0.6 L 0 2.2 L -0.6 0.6 L -2.2 0 L -0.6 -0.6 Z" fill="#ffffff" />
        </g>
      </g>
    </svg>
  );
}
