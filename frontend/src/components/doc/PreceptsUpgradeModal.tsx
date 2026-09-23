import { useEffect, useRef, useState } from "react";
import type { PreceptsUpgradePending } from "../../api";
import { MergeTool, type MergeToolHandle } from "../merge3/MergeTool";

type Props = {
  open: boolean;
  pending: PreceptsUpgradePending;
  proposing: boolean;
  busy: string | null;
  error: string | null;
  onClose: () => void;
  onConfirm: (body: string) => void;
  onDismiss: () => void;
  onUseOfficial: () => void;
};

type MergeStats = { chunks: number; pending: number; empty: boolean };

export function PreceptsUpgradeModal({
  open,
  pending,
  proposing,
  busy,
  error,
  onClose,
  onConfirm,
  onDismiss,
  onUseOfficial,
}: Props) {
  const toolRef = useRef<MergeToolHandle>(null);
  const [stats, setStats] = useState<MergeStats>({
    chunks: 0,
    pending: 0,
    empty: false,
  });

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose]);

  if (!open) return null;
  const locked = busy !== null;

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className="doc-history-modal doc-history-modal--frame precepts-merge-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="precepts-upgrade-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="doc-diff-header precepts-merge-top">
          <h3 id="precepts-upgrade-title">戒律更新</h3>
          {proposing ? (
            <span className="precepts-merge-proposing">官方建议稿生成中…</span>
          ) : null}
          <span className="precepts-merge-top-spacer" />
          <button
            type="button"
            className="doc-diff-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </header>
        <MergeTool
          ref={toolRef}
          base={pending.base}
          ours={pending.ours}
          theirs={pending.theirs}
          oursTitle="现行"
          theirsTitle="官方"
          className="merge3--modal"
          onStats={setStats}
          footer={
            <>
              <button
                type="button"
                className="doc-diff-btn"
                onClick={onDismiss}
                disabled={locked}
              >
                保持现行
              </button>
              <span className="precepts-merge-footer-note">
                {error
                  ? error
                  : stats.pending > 0
                    ? `还有 ${stats.pending} 处冲突待处理`
                    : "冲突都已处理，可直接写入"}
              </span>
              <span className="precepts-merge-footer-spacer" />
              <button
                type="button"
                className="doc-diff-btn"
                onClick={onUseOfficial}
                disabled={locked}
              >
                整篇用官方
              </button>
              <button
                type="button"
                className="doc-diff-btn doc-diff-btn--primary"
                onClick={() => {
                  const tool = toolRef.current;
                  if (tool) onConfirm(tool.getResultText());
                }}
                disabled={locked || stats.empty}
              >
                写入结果
              </button>
            </>
          }
        />
      </div>
    </div>
  );
}
