import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, Check, Trash } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  selectNotifications,
  selectUnreadCount,
  markAllRead,
  markRead,
  clearNotifications,
} from "@/store/notificationsSlice";

// Notification center (Task 19.7, Req 20.2). A header bell with an unread badge
// that opens a dropdown panel listing the in-app notifications received over the
// WebSocket (fed by useNotifications). Opening the panel marks everything read.

function formatWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NotificationCenter() {
  const dispatch = useAppDispatch();
  const items = useAppSelector(selectNotifications);
  const unread = useAppSelector(selectUnreadCount);
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onToggle = () => {
    setOpen((prev) => {
      const next = !prev;
      // Opening the panel marks everything as read (Req 20.2 surfacing).
      if (next && unread > 0) dispatch(markAllRead());
      return next;
    });
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={onToggle}
        aria-label={
          unread > 0 ? `Notifications (${unread} unread)` : "Notifications"
        }
        aria-haspopup="true"
        aria-expanded={open}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-foreground transition-colors hover:bg-accent"
      >
        <Bell size={18} />
        {unread > 0 ? (
          <span
            className="absolute -right-1 -top-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-4 text-primary-foreground"
            aria-hidden="true"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-lg border border-border bg-card text-card-foreground shadow-lg"
            role="menu"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">Notifications</span>
              {items.length > 0 ? (
                <button
                  type="button"
                  onClick={() => dispatch(clearNotifications())}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <Trash size={14} />
                  Clear
                </button>
              ) : null}
            </div>

            <div className="max-h-96 overflow-y-auto">
              {items.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  You&apos;re all caught up.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {items.map((n) => (
                    <li
                      key={n.id}
                      className={cn(
                        "flex items-start gap-3 px-4 py-3",
                        !n.read && "bg-accent/40"
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {n.title || "Notification"}
                        </p>
                        {n.body ? (
                          <p className="mt-0.5 text-sm text-muted-foreground">
                            {n.body}
                          </p>
                        ) : null}
                        <p className="mt-1 text-xs text-muted-foreground">
                          {formatWhen(n.receivedAt)}
                        </p>
                      </div>
                      {!n.read ? (
                        <button
                          type="button"
                          onClick={() => dispatch(markRead(n.id))}
                          aria-label="Mark as read"
                          title="Mark as read"
                          className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                        >
                          <Check size={14} />
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
