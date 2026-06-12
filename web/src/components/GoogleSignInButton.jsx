import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

// Google OAuth sign-in (Req 1.2). Uses Google Identity Services with the
// popup flow (works across Chrome, Edge, Firefox, Safari) instead of One Tap
// which only works reliably in Chrome.

const GIS_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

function loadGisScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts) {
      resolve(window.google);
      return;
    }
    const existing = document.querySelector(`script[src="${GIS_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve(window.google));
      existing.addEventListener("error", reject);
      return;
    }
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve(window.google);
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

export default function GoogleSignInButton({ onCredential, disabled, label = "Continue with Google" }) {
  const [ready, setReady] = useState(false);
  const initialized = useRef(false);
  const btnRef = useRef(null);
  const callbackRef = useRef(onCredential);
  callbackRef.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;
    loadGisScript()
      .then((google) => {
        if (cancelled || !google?.accounts?.id) return;
        if (!initialized.current) {
          google.accounts.id.initialize({
            client_id: CLIENT_ID,
            callback: (response) => {
              if (response?.credential) {
                callbackRef.current(response.credential);
              } else {
                toast.error("Google sign-in did not return a credential");
              }
            },
            ux_mode: "popup",
            use_fedcm_for_prompt: false,
          });
          initialized.current = true;
        }
        // Render an invisible Google button to use as cross-browser trigger
        if (btnRef.current) {
          google.accounts.id.renderButton(btnRef.current, {
            type: "icon",
            size: "large",
            width: 0,
          });
        }
        setReady(true);
      })
      .catch(() => {
        toast.error("Could not load Google sign-in");
      });
    return () => { cancelled = true; };
  }, []);

  const onClick = useCallback(() => {
    if (!CLIENT_ID) {
      toast.error("Google sign-in is not configured. Use email to sign in.");
      return;
    }
    if (!ready) {
      toast.error("Google sign-in is still loading");
      return;
    }
    // Click the hidden rendered Google button — works in all browsers
    const gBtn = btnRef.current?.querySelector('[role="button"]') ||
                 btnRef.current?.querySelector('div[style]') ||
                 btnRef.current?.firstChild;
    if (gBtn) {
      gBtn.click();
    } else {
      // Fallback: try prompt (Chrome) or show error
      try {
        window.google.accounts.id.prompt((notification) => {
          if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
            toast.error("Google popup was blocked. Allow popups and try again.");
          }
        });
      } catch {
        toast.error("Google sign-in failed. Try allowing popups.");
      }
    }
  }, [ready]);

  return (
    <>
      {/* Hidden Google-rendered button for cross-browser compatibility */}
      <div ref={btnRef} style={{ position: "absolute", opacity: 0, pointerEvents: "none", height: 0, overflow: "hidden" }} />
      <Button
        type="button"
        variant="outline"
        className="w-full"
        onClick={onClick}
        disabled={disabled}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" className="shrink-0">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
        </svg>
        {label}
      </Button>
    </>
  );
}
