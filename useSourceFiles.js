import { useState, useEffect, useCallback } from "react";
import { api } from "./api";

/**
 * Extracted so the Sync page and Upload page (split from the original
 * combined Source Files page) both show the same live batch list without
 * duplicating the polling logic.
 */
export function useSourceFiles(sessionId) {
  const [files, setFiles] = useState([]);
  const [error, setError] = useState(null);

  const refresh = useCallback(() => {
    api.listSourceFiles(sessionId).then(setFiles).catch((e) => setError(e.message));
  }, [sessionId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  return { files, error, refresh };
}
