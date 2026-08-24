import { useCallback, useEffect, useState } from "react";
import {
  getPublicShare,
  SharePublicError,
  type PublicSharePayload,
} from "../api/share";

export type PublicShareError = {
  status: number;
  message: string;
};

export function usePublicShare(shareId: string) {
  const [payload, setPayload] = useState<PublicSharePayload | null>(null);
  const [error, setError] = useState<PublicShareError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPublicShare(shareId)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          if (e instanceof SharePublicError) {
            setError({ status: e.status, message: e.message });
          } else {
            setError({
              status: 0,
              message: e instanceof Error ? e.message : "加载失败",
            });
          }
          setPayload(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shareId]);

  return { payload, error, loading };
}

export function useCopyShareUrl() {
  return useCallback(async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      return true;
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        return true;
      } catch {
        return false;
      }
    }
  }, []);
}
