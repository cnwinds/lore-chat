import { useCallback, useEffect, useState } from "react";
import {
  applyOfficialPrecepts,
  confirmPreceptsUpgrade,
  dismissPreceptsUpgrade,
  getPreceptsUpgrade,
  proposePreceptsUpgrade,
  type PreceptsUpgradePending,
} from "../../api";

function looksLikePrecepts(path: string) {
  return path.replace(/\\/g, "/").endsWith("戒律.md");
}

type Args = {
  path: string;
  onApplied?: () => void;
  onAttentionChange?: () => void;
};

export function usePreceptsUpgrade({ path, onApplied, onAttentionChange }: Args) {
  const [pending, setPending] = useState<PreceptsUpgradePending | null>(null);
  const [preceptsPath, setPreceptsPath] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabled = looksLikePrecepts(path);

  const applyStatus = useCallback(
    (data: { path: string; pending: PreceptsUpgradePending | null }) => {
      setPreceptsPath(data.path);
      if (data.path !== path) {
        setPending(null);
        return;
      }
      setPending(data.pending);
      onAttentionChange?.();
    },
    [onAttentionChange, path],
  );

  useEffect(() => {
    if (!enabled) {
      setPending(null);
      setReviewOpen(false);
      return;
    }
    let cancelled = false;
    setError(null);
    void getPreceptsUpgrade()
      .then(async (data) => {
        if (cancelled) return;
        applyStatus(data);
        if (data.applied && data.path === path) {
          onApplied?.();
        }
        if (
          data.path === path &&
          data.pending &&
          data.pending.proposed_source !== "ai"
        ) {
          setProposing(true);
          try {
            const next = await proposePreceptsUpgrade();
            if (!cancelled) applyStatus(next);
          } catch {
            /* 保留结构合并稿 */
          } finally {
            if (!cancelled) setProposing(false);
          }
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "无法读取戒律更新");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [applyStatus, enabled, path]);

  const run = useCallback(
    async (action: string, fn: () => Promise<{ pending: PreceptsUpgradePending | null; path: string; applied?: boolean }>) => {
      if (busy) return;
      setBusy(action);
      setError(null);
      try {
        const data = await fn();
        applyStatus(data);
        if (data.applied || !data.pending) {
          setReviewOpen(false);
          onApplied?.();
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "操作失败");
      } finally {
        setBusy(null);
      }
    },
    [applyStatus, busy, onApplied],
  );

  const confirm = useCallback(
    (body?: string) => run("confirm", () => confirmPreceptsUpgrade(body)),
    [run],
  );
  const dismiss = useCallback(
    () => run("dismiss", () => dismissPreceptsUpgrade()),
    [run],
  );
  const applyOfficial = useCallback(
    () => run("official", () => applyOfficialPrecepts()),
    [run],
  );

  const visible = Boolean(enabled && pending && preceptsPath === path);

  return {
    visible,
    pending: visible ? pending : null,
    reviewOpen,
    setReviewOpen,
    proposing,
    busy,
    error,
    confirm,
    dismiss,
    applyOfficial,
  };
}
