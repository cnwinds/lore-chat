import { useEffect, useMemo, useState } from "react";
import type { PreceptsUpgradePending } from "../../api";
import { buildDocDiff } from "../../utils/docDiff";

type View = "conflicts" | "proposed" | "diff";

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
  const [view, setView] = useState<View>("conflicts");
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState(pending.proposed);
  const [edited, setEdited] = useState(false);

  useEffect(() => {
    if (!open) return;
    setView(pending.conflicts.length ? "conflicts" : "proposed");
    setSelected(0);
    setDraft(pending.proposed);
    setEdited(false);
  }, [open, pending.created_at]);

  useEffect(() => {
    if (!edited) setDraft(pending.proposed);
  }, [edited, pending.proposed]);

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

  const hunk = pending.conflicts[selected] ?? pending.conflicts[0];
  const diffLines = useMemo(
    () => buildDocDiff(pending.ours, draft),
    [draft, pending.ours],
  );

  if (!open) return null;
  const locked = busy !== null;

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className="doc-history-modal doc-history-modal--frame"
        role="dialog"
        aria-modal="true"
        aria-labelledby="precepts-upgrade-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="doc-diff-header">
          <h3 id="precepts-upgrade-title">戒律更新</h3>
          <button
            type="button"
            className="doc-diff-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </header>
        <div className="doc-history-main">
          <aside className="doc-history-list" aria-label="冲突列表">
            {pending.conflicts.length === 0 ? (
              <p className="doc-diff-empty">没有冲突块。</p>
            ) : (
              pending.conflicts.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  className={`doc-history-item${selected === i ? " is-active" : ""}`}
                  onClick={() => {
                    setView("conflicts");
                    setSelected(i);
                  }}
                >
                  <span className="doc-history-item-time">冲突 {i + 1}</span>
                </button>
              ))
            )}
          </aside>
          <section className="doc-history-pane">
            <div className="doc-history-pane-bar">
              <div className="doc-history-switch" role="group" aria-label="查看方式">
                <button
                  type="button"
                  className={view === "conflicts" ? "is-active" : undefined}
                  onClick={() => setView("conflicts")}
                  disabled={!hunk}
                >
                  冲突
                </button>
                <button
                  type="button"
                  className={view === "proposed" ? "is-active" : undefined}
                  onClick={() => setView("proposed")}
                >
                  合并稿
                </button>
                <button
                  type="button"
                  className={view === "diff" ? "is-active" : undefined}
                  onClick={() => setView("diff")}
                >
                  对照
                </button>
              </div>
            </div>
            <div className="doc-history-pane-body">
              {error ? <p className="doc-diff-empty">{error}</p> : null}
              {proposing ? <p className="doc-diff-empty">正在生成合并稿…</p> : null}
              {view === "conflicts" && hunk ? (
                <div className="doc-precepts-hunks">
                  <HunkBlock label="当前" text={hunk.ours} />
                  <HunkBlock label="新官方" text={hunk.theirs} />
                  {hunk.base ? <HunkBlock label="上次官方" text={hunk.base} /> : null}
                </div>
              ) : view === "proposed" ? (
                <textarea
                  className="doc-precepts-draft"
                  value={draft}
                  onChange={(e) => {
                    setEdited(true);
                    setDraft(e.target.value);
                  }}
                  spellCheck={false}
                />
              ) : (
                <pre className="doc-diff-lines">
                  {diffLines.map((line, i) => (
                    <div
                      key={i}
                      className={`doc-diff-line doc-diff-line--${line.type}`}
                    >
                      <span className="doc-diff-gutter" aria-hidden>
                        {line.type === "added"
                          ? "+"
                          : line.type === "removed"
                            ? "−"
                            : " "}
                      </span>
                      <span className="doc-diff-text">{line.content || " "}</span>
                    </div>
                  ))}
                </pre>
              )}
            </div>
          </section>
        </div>
        <footer className="doc-diff-footer">
          <button
            type="button"
            className="doc-diff-btn"
            onClick={onUseOfficial}
            disabled={locked}
          >
            用官方稿
          </button>
          <button
            type="button"
            className="doc-diff-btn"
            onClick={onDismiss}
            disabled={locked}
          >
            保持
          </button>
          <button
            type="button"
            className="doc-diff-btn doc-diff-btn--primary"
            onClick={() => onConfirm(draft)}
            disabled={locked || proposing || !draft.trim()}
          >
            采用
          </button>
        </footer>
      </div>
    </div>
  );
}

function HunkBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="doc-precepts-hunk">
      <div className="doc-precepts-hunk-label">{label}</div>
      <pre className="doc-history-text">{text || "（空）"}</pre>
    </div>
  );
}
