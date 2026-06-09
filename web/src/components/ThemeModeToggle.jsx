import { Moon, Sun } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectMode, setMode } from "@/store/authSlice";
import { cn } from "@/lib/utils";

// Light/dark toggle (Req 4.4). The reducer applies the mode first and only
// persists on success; if applying fails, state.mode stays unchanged and we
// surface the failure to the user instead of silently persisting.
export default function ThemeModeToggle({ className }) {
  const dispatch = useAppDispatch();
  const mode = useAppSelector(selectMode);
  const next = mode === "dark" ? "light" : "dark";

  const onToggle = () => {
    dispatch(setMode(next));
    // Read back: if the DOM still reflects the old mode, the toggle failed.
    const applied = document.documentElement.classList.contains("dark");
    if ((next === "dark") !== applied) {
      toast.error("Could not switch theme mode");
    }
  };

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={`Switch to ${next} mode`}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-foreground transition-colors hover:bg-accent",
        className
      )}
    >
      {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
