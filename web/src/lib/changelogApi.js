import apiClient from "@/lib/apiClient";

// Changelog / "What's new" API surface (Task 19.7, Req 22.1, 22.2). Maps 1:1 to
// the backend endpoints in app/api/v1/changelog.py and returns the parsed body.
// The changelog is platform-wide so these reads only require an authenticated
// principal (no tenant scoping).

/**
 * List all published changelog entries, newest first (Req 22.1).
 *
 * @returns {Promise<Array<{
 *   id: string, version: string|null, title: string|null,
 *   body: string|null, published_at: string|null
 * }>>}
 */
export async function listChangelog() {
  const { data } = await apiClient.get("/changelog");
  return data.entries; // { entries } -> entries
}

/**
 * Fetch the entries published since the caller last viewed the changelog. The
 * "What's new" popup is shown when `show_popup` is true (Req 22.2).
 *
 * @returns {Promise<{ show_popup: boolean, entries: Array<object> }>}
 */
export async function getUnseenChangelog() {
  const { data } = await apiClient.get("/changelog/unseen");
  return data; // { show_popup, entries }
}

/**
 * Mark the changelog as seen so the "What's new" popup does not reappear for the
 * current entries (Req 22.2).
 *
 * @returns {Promise<{ last_seen_at: string }>}
 */
export async function markChangelogSeen() {
  const { data } = await apiClient.post("/changelog/seen");
  return data; // { last_seen_at }
}
