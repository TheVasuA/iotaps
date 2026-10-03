import { useEffect, useRef } from "react";

/** Pick up id_token from OAuth redirect (#id_token=...) on /login, /register, /settings, etc. */
export function useGoogleRedirectCredential(onCredential) {
  const handler = useRef(onCredential);
  handler.current = onCredential;

  useEffect(() => {
    if (typeof handler.current !== "function") return;

    const hash = window.location.hash;
    if (!hash || !hash.includes("id_token=")) return;

    const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
    const idToken = params.get("id_token");
    if (!idToken) return;

    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    handler.current(idToken);
  }, [onCredential]);
}
