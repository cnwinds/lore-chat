import { useEffect, useMemo } from "react";
import { buildDocDiff } from "../utils/docDiff";

type Props = {
  open: boolean;
  saved: string;
  current: string;
  onClose: () => void;
  onDiscard?: () => void;
  onSave?: () => void;
  saving?: boolean;
};

export function DocDiffModal({
  open,
  saved,
  current,
  onClose,
  onDiscard,
  onSave,
  saving = false,
}: Props) {
  const lines = useMemo(() => buildDocDiff(saved, current), [saved, current]);
  const hasChanges = lines.some((l) => l.type !== "unchanged");

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

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className="doc-diff-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="doc-diff-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="doc-diff-header">
          <h3 id="doc-diff-title">查看变更</h3>
          <button type="button" className="doc-diff-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>
        <div className="doc-diff-body">
          {!hasChanges ? (
            <p className="doc-diff-empty">当前内容与已保存版本相同。</p>
          ) : (
            <pre className="doc-diff-lines">
              {lines.map((line, i) => (
                <div
                  key={i}
                  className={`doc-diff-line doc-diff-line--${line.type}`}
                >
                  <span className="doc-diff-gutter" aria-hidden>
                    {line.type === "added" ? "+" : line.type === "removed" ? "−" : " "}
                  </span>
                  <span className="doc-diff-text">{line.content || " "}</span>
                </div>
              ))}
            </pre>
          )}
        </div>
        <footer className="doc-diff-footer">
          <button type="button" className="doc-diff-btn" onClick={onClose}>
            关闭
          </button>
          {onDiscard && (
            <button
              type="button"
              className="doc-diff-btn doc-diff-btn--danger"
              onClick={onDiscard}
              disabled={saving}
            >
              放弃修改
            </button>
          )}
          {onSave && (
            <button
              type="button"
              className="doc-diff-btn doc-diff-btn--primary"
              onClick={onSave}
              disabled={saving}
            >
              {saving ? "保存中…" : "保存"}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
