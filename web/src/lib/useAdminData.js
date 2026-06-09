import { useCallback, useEffect, useState } from "react";
import { extractApiError } from "@/lib/authApi";

// Small data-loading hook shared by the Super_Admin panels (Task 20.7).
// Runs `loader` on mount (and whenever `deps` change), tracking
// loading/succeeded/failed status and exposing a `reload` for mutations.
export default function useAdminData(loader, deps = []) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | succeeded | failed
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    setStatus("loading");
    setError(null);
    try {
      const result = await loader();
      if (!signal?.cancelled) {
        setData(result);
        setStatus("succeeded");
      }
    } catch (err) {
      if (!signal?.cancelled) {
        setError(extractApiError(err).message);
        setStatus("failed");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load]);

  const reload = useCallback(() => load(), [load]);

  return { data, status, error, setData, reload };
}
