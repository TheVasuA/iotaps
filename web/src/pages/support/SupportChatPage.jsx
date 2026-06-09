import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CircleNotch, PaperPlaneTilt, ChatCircleText } from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  listSupportMessages,
  sendSupportMessage,
  replySupportMessage,
} from "@/lib/supportApi";
import { listDevices } from "@/lib/devicesApi";
import { extractApiError } from "@/lib/authApi";
import { useAppSelector } from "@/store/hooks";
import { selectRole } from "@/store/authSlice";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Support chat thread (Task 19.7, Req 21.1, 21.2, 21.3).
//
// Device_User: picks one of their assigned devices and sends a message about it;
// the backend routes it to the device's Project_Center with the device identity
// (Req 21.1, 21.2). Project_Center: sees incoming messages and replies, routed
// back to the originating Device_User (Req 21.3).
//
// Messages are grouped into per-device threads. The composer sends a new
// Device_User message (for device users) or replies to the latest message in
// the thread (for project centers).

function deviceLabel(device) {
  if (!device) return null;
  return device.label || device.device_uid || device.id;
}

function timeLabel(iso) {
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

function MessageBubble({ message, mine }) {
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-lg px-3 py-2 text-sm",
          mine
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-card text-card-foreground"
        )}
      >
        <p className="whitespace-pre-line break-words">{message.message}</p>
        <p
          className={cn(
            "mt-1 text-[10px]",
            mine ? "text-primary-foreground/70" : "text-muted-foreground"
          )}
        >
          {message.sender_role === "project_center"
            ? "Support"
            : message.sender_role === "device_user"
              ? "You"
              : message.sender_role || ""}
          {message.created_at ? ` · ${timeLabel(message.created_at)}` : ""}
        </p>
      </div>
    </div>
  );
}

export default function SupportChatPage() {
  const role = useAppSelector(selectRole);
  const isProjectCenter = role === "project_center";

  const [devices, setDevices] = useState([]);
  const [messages, setMessages] = useState([]);
  const [activeDeviceId, setActiveDeviceId] = useState(null);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("loading"); // loading | succeeded | failed
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const threadEndRef = useRef(null);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [deviceList, messageList] = await Promise.all([
        listDevices().catch(() => []),
        listSupportMessages(),
      ]);
      setDevices(deviceList);
      setMessages(messageList);
      setStatus("succeeded");
      // Default the active thread to the first device that has any context.
      setActiveDeviceId((current) => {
        if (current) return current;
        const fromMessages = messageList.find((m) => m.device_id)?.device_id;
        return fromMessages || deviceList[0]?.id || null;
      });
    } catch (err) {
      setError(extractApiError(err).message);
      setStatus("failed");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Per-device threads: every device the caller can see plus any device that
  // already appears in the message history.
  const threads = useMemo(() => {
    const byId = new Map();
    for (const device of devices) {
      byId.set(device.id, { deviceId: device.id, label: deviceLabel(device) });
    }
    for (const m of messages) {
      if (m.device_id && !byId.has(m.device_id)) {
        byId.set(m.device_id, {
          deviceId: m.device_id,
          label: m.device_id,
        });
      }
    }
    return Array.from(byId.values());
  }, [devices, messages]);

  const threadMessages = useMemo(() => {
    if (!activeDeviceId) return [];
    return messages
      .filter((m) => m.device_id === activeDeviceId)
      .slice()
      .sort((a, b) =>
        String(a.created_at || "").localeCompare(String(b.created_at || ""))
      );
  }, [messages, activeDeviceId]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [threadMessages.length]);

  const onSend = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !activeDeviceId || sending) return;
    setSending(true);
    try {
      let created;
      if (isProjectCenter) {
        // Reply to the most recent message in the thread (Req 21.3).
        const last = threadMessages[threadMessages.length - 1];
        if (!last) {
          toast.error("No message to reply to yet");
          setSending(false);
          return;
        }
        created = await replySupportMessage(last.id, text);
      } else {
        // Device_User sends a new message about the selected device (Req 21.1).
        created = await sendSupportMessage({
          deviceId: activeDeviceId,
          message: text,
        });
      }
      setMessages((prev) => [...prev, created]);
      setDraft("");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setSending(false);
    }
  };

  const activeThread = threads.find((t) => t.deviceId === activeDeviceId);

  return (
    <section className="mx-auto flex h-[calc(100vh-8rem)] max-w-5xl flex-col">
      <header className="mb-4">
        <h1 className="text-2xl font-semibold text-primary">Support</h1>
        <p className="text-sm text-muted-foreground">
          {isProjectCenter
            ? "Reply to device users about their assigned devices."
            : "Chat with your provider about a specific device."}
        </p>
      </header>

      {status === "loading" ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <CircleNotch size={24} className="animate-spin" />
        </div>
      ) : status === "failed" ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-destructive">
          {error || "Failed to load support chat"}
        </div>
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden md:grid-cols-[16rem_1fr]">
          {/* Thread list (per device) */}
          <aside className="overflow-y-auto rounded-lg border border-border bg-card">
            {threads.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">
                No devices available.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {threads.map((t) => {
                  const unread = messages.some(
                    (m) => m.device_id === t.deviceId
                  );
                  return (
                    <li key={t.deviceId}>
                      <button
                        type="button"
                        onClick={() => setActiveDeviceId(t.deviceId)}
                        className={cn(
                          "flex w-full items-center gap-2 px-4 py-3 text-left text-sm transition-colors hover:bg-accent",
                          activeDeviceId === t.deviceId &&
                            "bg-accent text-accent-foreground"
                        )}
                      >
                        <ChatCircleText size={18} className="shrink-0" />
                        <span className="truncate">{t.label}</span>
                        {unread ? (
                          <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>

          {/* Active thread */}
          <div className="flex min-h-0 flex-col rounded-lg border border-border bg-background">
            <div className="border-b border-border px-4 py-3">
              <p className="text-sm font-medium text-foreground">
                {activeThread ? activeThread.label : "Select a device"}
              </p>
              <p className="text-xs text-muted-foreground">
                Device support thread
              </p>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {threadMessages.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No messages yet.
                  {isProjectCenter
                    ? " Replies appear once a device user reaches out."
                    : " Send a message to start the conversation."}
                </p>
              ) : (
                threadMessages.map((m) => (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    mine={
                      isProjectCenter
                        ? m.sender_role === "project_center"
                        : m.sender_role === "device_user"
                    }
                  />
                ))
              )}
              <div ref={threadEndRef} />
            </div>

            <form
              onSubmit={onSend}
              className="flex items-center gap-2 border-t border-border p-3"
            >
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={
                  activeDeviceId
                    ? isProjectCenter
                      ? "Type a reply…"
                      : "Type a message…"
                    : "Select a device first"
                }
                disabled={!activeDeviceId || sending}
                aria-label="Message"
              />
              <Button
                type="submit"
                disabled={!activeDeviceId || sending || !draft.trim()}
                aria-label="Send message"
              >
                {sending ? (
                  <CircleNotch size={16} className="animate-spin" />
                ) : (
                  <PaperPlaneTilt size={16} />
                )}
                <span className="hidden sm:inline">Send</span>
              </Button>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
