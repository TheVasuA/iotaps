import { useEffect, useState } from "react";
import { QrCode } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { fetchDeviceQrUrl } from "@/lib/devicesApi";

// Renders the device QR code (Req 5.2). The backend serves a PNG at
// /devices/{id}/qr; we fetch it as a blob (the shared apiClient attaches the
// JWT) and display it via an object URL, revoking the URL on unmount/refetch.
// `payload` is the QR text and is shown for reference.
export default function QrDisplay({ deviceId, payload, className }) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId) return undefined;
    let revoked = false;
    let objectUrl = null;
    setLoading(true);
    setError(false);
    fetchDeviceQrUrl(deviceId)
      .then((u) => {
        objectUrl = u;
        if (!revoked) setUrl(u);
      })
      .catch(() => {
        if (!revoked) setError(true);
      })
      .finally(() => {
        if (!revoked) setLoading(false);
      });
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [deviceId]);

  return (
    <div
      className={cn(
        "flex w-fit flex-col items-center gap-2 rounded-lg border border-border bg-background p-4",
        className
      )}
    >
      {loading ? (
        <div className="flex h-40 w-40 items-center justify-center text-muted-foreground">
          <QrCode size={40} className="animate-pulse" />
        </div>
      ) : error ? (
        <div className="flex h-40 w-40 flex-col items-center justify-center gap-2 text-center text-xs text-muted-foreground">
          <QrCode size={32} />
          Could not load QR code
        </div>
      ) : (
        <img
          src={url}
          alt="Device QR code"
          className="h-40 w-40 rounded bg-white"
        />
      )}
      {payload ? (
        <code className="max-w-[12rem] truncate text-[11px] text-muted-foreground">
          {payload}
        </code>
      ) : null}
    </div>
  );
}
