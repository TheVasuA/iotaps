import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn/ui className helper: merge conditional classes and de-dupe Tailwind
// utility conflicts (e.g. "px-2" + "px-4" -> "px-4").
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
