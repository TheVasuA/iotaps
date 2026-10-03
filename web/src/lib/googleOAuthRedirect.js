const NONCE_KEY = "iotaps.google.oauth.nonce";

function randomNonce() {
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Redirect-based Google sign-in (works when GIS iframe/button is blocked). */
export function startGoogleOAuthRedirect(clientId, returnPath) {
  const id = (clientId || "").trim();
  if (!id) {
    throw new Error("missing_client_id");
  }
  const nonce = randomNonce();
  try {
    sessionStorage.setItem(NONCE_KEY, nonce);
  } catch {
    /* ignore */
  }
  const redirectUri = `${window.location.origin}${returnPath || window.location.pathname}`;
  const params = new URLSearchParams({
    client_id: id,
    redirect_uri: redirectUri,
    response_type: "id_token",
    scope: "openid email profile",
    nonce,
    prompt: "select_account",
  });
  window.location.assign(`https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`);
}

export function consumeGoogleRedirectNonce() {
  try {
    const n = sessionStorage.getItem(NONCE_KEY);
    sessionStorage.removeItem(NONCE_KEY);
    return n;
  } catch {
    return null;
  }
}
