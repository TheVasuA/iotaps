import { cn } from "@/lib/utils";

/** Blynk-style lime square mark with a bold initial (IoTAPS console / auth). */
export default function BrandMark({ size = 40, letter = "I", className }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center bg-primary font-brand font-bold leading-none text-primary-foreground",
        className
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.52) }}
      aria-hidden={letter ? undefined : true}
      role={letter ? "img" : undefined}
      aria-label={letter ? "IoTAPS" : undefined}
    >
      {letter}
    </span>
  );
}
