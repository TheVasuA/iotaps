// Theme groundwork for the three role themes + light/dark mode (Req 4.1-4.4).
//
// Role -> theme mapping:
//   super_admin     -> purple        (data-theme="admin")        Req 4.1
//   project_center  -> light yellow  (data-theme="project-center") Req 4.2
//   device_user     -> blue-light    (data-theme="device-user")  Req 4.3
//
// Visual mode is "light" | "dark" and is persisted per user (Req 4.4). If the
// mode cannot be applied to the DOM, the toggle fails WITHOUT persisting the
// new preference (Req 4.4 failure clause).

export const ROLE_THEME = {
  super_admin: "admin",
  project_center: "project-center",
  device_user: "device-user",
};

export const VISUAL_MODES = ["light", "dark"];
const MODE_STORAGE_KEY = "iotaps.theme.mode";

/** Resolve a backend role string to its theme token, defaulting safely. */
export function themeForRole(role) {
  return ROLE_THEME[role] || "admin";
}

/** Apply the role theme to <html>. Returns true on success. */
export function applyRoleTheme(role) {
  const theme = themeForRole(role);
  const root = document.documentElement;
  if (!root) return false;
  root.setAttribute("data-theme", theme);
  return true;
}

/**
 * Apply a visual mode ("light"/"dark") to <html>.
 * Returns true if applied, false if the mode is invalid or the DOM is missing.
 * This is the operation that may "fail" per Req 4.4.
 */
export function applyVisualMode(mode) {
  if (!VISUAL_MODES.includes(mode)) return false;
  const root = document.documentElement;
  if (!root || typeof root.classList === "undefined") return false;
  root.classList.toggle("dark", mode === "dark");
  root.style.colorScheme = mode;
  return true;
}

/** Read the persisted visual mode, falling back to "light". */
export function loadPersistedMode() {
  try {
    const stored = localStorage.getItem(MODE_STORAGE_KEY);
    return VISUAL_MODES.includes(stored) ? stored : "light";
  } catch {
    return "light";
  }
}

/** Persist the visual mode preference. Returns true on success. */
export function persistMode(mode) {
  try {
    localStorage.setItem(MODE_STORAGE_KEY, mode);
    return true;
  } catch {
    return false;
  }
}

/**
 * Toggle/set the visual mode with Req 4.4 semantics:
 *   - apply first; only persist if the apply succeeded.
 *   - if apply fails, do NOT persist and report failure.
 * @returns {{ ok: boolean, mode: string }}
 */
export function setVisualMode(mode) {
  const applied = applyVisualMode(mode);
  if (!applied) {
    return { ok: false, mode: loadPersistedMode() };
  }
  persistMode(mode);
  return { ok: true, mode };
}

/** Initialize theme on app boot from a role and any persisted mode. */
export function initTheme(role) {
  applyRoleTheme(role);
  applyVisualMode(loadPersistedMode());
}
