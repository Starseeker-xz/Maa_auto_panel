import React from "react";

export function usePolling(callback: () => void | Promise<void>, { enabled = true, intervalMs = 1000 }: { enabled?: boolean; intervalMs?: number } = {}) {
  const callbackRef = React.useRef(callback);

  React.useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  React.useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const timer = window.setInterval(() => {
      if (!cancelled) void callbackRef.current();
    }, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs]);
}
