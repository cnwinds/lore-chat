import { useCallback, useEffect, useRef, useState } from "react";
import {
  getPublicShare,
  SHARE_PASSWORD_REQUIRED,
  SharePublicError,
  shareUnlockStorageKey,
  unlockShare,
  type PublicSharePayload,
} from "../api/share";
import { copyTextToClipboard } from "../utils/clipboard";

export type PublicShareError = {
  status: number;
  message: string;
  code?: string;
};

function readStoredUnlock(shareId: string): string | null {
  try {
    return sessionStorage.getItem(shareUnlockStorageKey(shareId));
  } catch {
    return null;
  }
}

export function usePublicShare(shareId: string) {
  const [payload, setPayload] = useState<PublicSharePayload | null>(null);
  const [error, setError] = useState<PublicShareError | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsPassword, setNeedsPassword] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const shareIdRef = useRef(shareId);
  shareIdRef.current = shareId;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setUnlockError(null);
    setPayload(null);
    setNeedsPassword(false);

    void getPublicShare(shareId, readStoredUnlock(shareId))
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setNeedsPassword(false);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setPayload(null);
        if (e instanceof SharePublicError && e.code === SHARE_PASSWORD_REQUIRED) {
          setNeedsPassword(true);
          setError(null);
        } else if (e instanceof SharePublicError) {
          setNeedsPassword(false);
          setError({ status: e.status, message: e.message, code: e.code });
        } else {
          setNeedsPassword(false);
          setError({
            status: 0,
            message: e instanceof Error ? e.message : "加载失败",
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [shareId]);

  const submitPassword = useCallback(async (password: string) => {
    const id = shareIdRef.current;
    setUnlocking(true);
    setUnlockError(null);
    try {
      const res = await unlockShare(id, password);
      try {
        sessionStorage.setItem(shareUnlockStorageKey(id), res.unlock_token);
      } catch {
        /* private mode */
      }
      // 先离开密码门，再拉 payload，避免中间态主区空白
      setNeedsPassword(false);
      setLoading(true);
      try {
        const data = await getPublicShare(id, res.unlock_token);
        if (shareIdRef.current !== id) return;
        setPayload(data);
        setError(null);
      } catch (e: unknown) {
        if (shareIdRef.current !== id) return;
        // 解锁已成功；加载失败时不回到密码门（token 已写入 sessionStorage）
        if (e instanceof SharePublicError) {
          setError({ status: e.status, message: e.message, code: e.code });
        } else {
          setError({
            status: 0,
            message: e instanceof Error ? e.message : "加载失败",
          });
        }
      }
    } catch (e: unknown) {
      if (shareIdRef.current !== id) return;
      if (e instanceof SharePublicError && e.code === SHARE_PASSWORD_REQUIRED) {
        setNeedsPassword(true);
        setUnlockError(e.message || "需要重新输入密码");
      } else if (e instanceof SharePublicError) {
        // 解锁失败：留在密码门；GET 失败：按状态展示
        if (e.status === 401) {
          setNeedsPassword(true);
          setUnlockError(e.message || "密码错误");
        } else {
          setNeedsPassword(false);
          setError({ status: e.status, message: e.message, code: e.code });
        }
      } else {
        setNeedsPassword(true);
        setUnlockError(e instanceof Error ? e.message : "解锁失败");
      }
    } finally {
      if (shareIdRef.current === id) {
        setUnlocking(false);
        setLoading(false);
      }
    }
  }, []);

  return {
    payload,
    error,
    loading,
    needsPassword,
    unlocking,
    unlockError,
    submitPassword,
  };
}

export function useCopyShareUrl() {
  return useCallback(async (url: string) => copyTextToClipboard(url), []);
}
