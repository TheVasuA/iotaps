import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import axios from "axios";
import { API_BASE_URL } from "@/lib/apiClient";
import { startGoogleOAuthRedirect } from "@/lib/googleOAuthRedirect";

const GIS_SRC = "https://accounts.google.com/gsi/client";
const BUILD_TIME_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim();

function loadGisScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) {
      resolve(window.google);
      return;
    }
    const existing = document.querySelector(`script[src="${GIS_SRC}"]`);
    if (existing) {
      if (window.google?.accounts?.id) {
        resolve(window.google);
        return;
      }
      existing.addEventListener("load", () => resolve(window.google), { once: true });
      existing.addEventListener("error", () => reject(new Error("gis_load_failed")), {
        once: true,
      });
      return;
    }
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve(window.google);
    script.onerror = () => reject(new Error("gis_load_failed"));
    document.head.appendChild(script);
  });
}

export async function resolveGoogleClientId() {
  if (BUILD_TIME_CLIENT_ID) return BUILD_TIME_CLIENT_ID;
  try {
    const { data } = await axios.get(`${API_BASE_URL}/public/oauth-config`, {
      timeout: 8000,
    });
    return (data?.google_client_id || "").trim();
  } catch {
    return "";
  }
}

export default function GoogleSignInButton({
  onCredential,
  disabled,
  label = "Continue with Google",
  showRedirectLink = true,
  redirectReturnPath,
}) {
  const containerRef = useRef(null);
  const [clientId, setClientId] = useState(BUILD_TIME_CLIENT_ID);
  const [configReady, setConfigReady] = useState(!!BUILD_TIME_CLIENT_ID);
  const [ready, setReady] = useState(false);
  const [useFallback, setUseFallback] = useState(false);
  const [loadingFallback, setLoadingFallback] = useState(false);
  const callbackRef = useRef(onCredential);
  const initializedRef = useRef(false);
  callbackRef.current = onCredential;

  const initGoogle = useCallback(
    async (id, { force = false } = {}) => {
      if (!id) return false;
      if (initializedRef.current && !force) return true;
      const google = await loadGisScript();
      if (!google?.accounts?.id || !containerRef.current) return false;

      containerRef.current.innerHTML = "";
      initializedRef.current = false;

      google.accounts.id.initialize({
        client_id: id,
        callback: (response) => {
          if (response?.credential) {
            callbackRef.current(response.credential);
          } else {
            toast.error("Google sign-in did not return a credential");
          }
        },
        ux_mode: "popup",
        itp_support: true,
        use_fedcm_for_prompt: false,
      });

      const width = containerRef.current.offsetWidth || 360;
      google.accounts.id.renderButton(containerRef.current, {
        type: "standard",
        theme: "outline",
        size: "large",
        width: Math.min(Math.max(width, 280), 400),
        text: label.toLowerCase().includes("sign up") ? "signup_with" : "continue_with",
        locale: "en",
        shape: "rectangular",
      });

      initializedRef.current = true;
      return true;
    },
    [label]
  );

  useEffect(() => {
    let cancelled = false;
    let timeoutId;

    (async () => {
      const id = await resolveGoogleClientId();
      if (cancelled) return;
      setConfigReady(true);
      if (!id) {
        setUseFallback(true);
        return;
      }
      setClientId(id);

      try {
        const ok = await initGoogle(id);
        if (cancelled) return;
        if (ok) {
          setReady(true);
          timeoutId = window.setTimeout(() => {
            const hasButton = containerRef.current?.querySelector("iframe, div[role=button]");
            if (!hasButton) setUseFallback(true);
          }, 3500);
        } else {
          setUseFallback(true);
        }
      } catch {
        if (!cancelled) setUseFallback(true);
      }
    })();

    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
      initializedRef.current = false;
    };
  }, [initGoogle, label]);

  const onFallbackClick = async () => {
    if (disabled || loadingFallback) return;
    setLoadingFallback(true);
    try {
      const id = clientId || (await resolveGoogleClientId());
      if (!id) {
        toast.error("Google sign-in is not configured on this server");
        return;
      }
      setClientId(id);
      const ok = await initGoogle(id, { force: true });
      if (ok) {
        setReady(true);
        setUseFallback(false);
        const hasButton = containerRef.current?.querySelector("iframe, div[role=button]");
        if (hasButton) {
          hasButton.click?.();
          return;
        }
        window.google?.accounts?.id?.prompt((notification) => {
          if (notification?.isNotDisplayed?.()) {
            const reason = notification.getNotDisplayedReason?.() || "blocked";
            toast.error(
              reason === "browser_not_supported"
                ? "Try Chrome or allow pop-ups for Google sign-in"
                : "Google sign-in blocked — allow pop-ups or disable strict tracking protection"
            );
            setUseFallback(true);
          }
        });
      } else {
        toast.error("Could not start Google sign-in");
      }
    } catch {
      toast.error("Could not load Google sign-in. Check your connection or try another browser.");
    } finally {
      setLoadingFallback(false);
    }
  };

  if (!configReady) {
    return (
      <div className="auth-google-wrap flex h-11 w-full animate-pulse items-center justify-center rounded border border-border bg-muted/30 text-xs text-muted-foreground">
        Loading sign-in…
      </div>
    );
  }

  if (!clientId) {
    return (
      <p className="text-center text-xs text-muted-foreground">
        Google sign-in is not configured for this environment.
      </p>
    );
  }

  return (
    <div className="auth-google-wrap flex min-h-[44px] w-full flex-col gap-2">
      {!useFallback ? (
        <div
          ref={containerRef}
          className={
            disabled
              ? "pointer-events-none flex min-h-[44px] w-full items-center justify-center opacity-50"
              : "flex min-h-[44px] w-full items-center justify-center [&>div]:!w-full"
          }
          aria-busy={!ready}
        />
      ) : (
        <div ref={containerRef} className="hidden" aria-hidden />
      )}
      {showRedirectLink && clientId ? (
        <button
          type="button"
          disabled={disabled}
          className="text-center text-xs font-medium text-primary hover:underline disabled:opacity-50"
          onClick={() => {
            try {
              startGoogleOAuthRedirect(clientId, redirectReturnPath || window.location.pathname);
            } catch {
              toast.error("Google sign-in is not configured");
            }
          }}
        >
          Trouble with the button? Use Google sign-in link
        </button>
      ) : null}
      {useFallback ? (
        <button
          type="button"
          disabled={disabled || loadingFallback}
          onClick={onFallbackClick}
          className="auth-google-fallback flex h-11 w-full items-center justify-center gap-2 border border-zinc-200 bg-white text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50 disabled:opacity-50 dark:border-border dark:bg-card dark:text-foreground dark:hover:bg-muted/40"
        >
          <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
            <path
              fill="#EA4335"
              d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
            />
            <path
              fill="#4285F4"
              d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.56 2.96-2.23 5.48-4.76 7.15l7.73 6.01C42.44 39.68 46.98 33.08 46.98 24.55z"
            />
            <path
              fill="#FBBC05"
              d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
            />
            <path
              fill="#34A853"
              d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6.01c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
            />
          </svg>
          {loadingFallback ? "Loading…" : label}
        </button>
      ) : null}
    </div>
  );
}
