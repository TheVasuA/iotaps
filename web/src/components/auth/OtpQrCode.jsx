import { cn } from "@/lib/utils";

/** Render a QR code for an otpauth:// URI (authenticator apps). */
export default function OtpQrCode({ uri, size = 180, className }) {
  if (!uri) return null;
  const src = `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(uri)}`;
  return (
    <img
      src={src}
      width={size}
      height={size}
      alt="Scan with authenticator app"
      className={cn("rounded-lg border border-border bg-white p-2", className)}
    />
  );
}
