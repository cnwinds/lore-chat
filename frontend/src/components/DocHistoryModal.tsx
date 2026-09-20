import { useEffect, useMemo, useState } from "react";
import {
  getDocRevision,
  listDocRevisions,
  type DocRevisionBody,
  type DocRevisionInfo,
} from "../api";
import { buildDocDiff } from "../utils/docDiff";
import { formatRoutineRunTime } from "../utils/displayTime";
import { DiffIcon, DocIconBtn } from "./DocToolbarIcons";

type Props = {
  open: boolean;
  path: string | null;
  onClose: () => void;
};

export function DocHistoryModal({ open, path, onClose }: Props) {
  const [revisions, setRevisions] = useState<DocRevisionInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<DocRevisionBody | null>(null);
  const [olderText, setOlderText] = useState<string | null>(null);
  const [comparePrev, setComparePrev] = useState(true);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingBody, setLoadingBody] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !path) return;
    let cancelled = false;
    setLoadingList(true);
    setError(null);
    setRevisions([]);
    setSelected(null);
    setCurrent(null);
    setOlderText(null);
    setComparePrev(true);
    void listDocRevisions(path)
      .then((data) => {
        if (cancelled) return;
        setRevisions(data.revisions);
        setSelected(data.revisions[0]?.sha ?? null);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "无法读取修订");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, path]);

  useEffect(() => {
    if (!open || !path || !selected) return;
    let cancelled = false;
    setLoadingBody(true);
    const index = revisions.findIndex((r) => r.sha === selected);
    const olderSha = index >= 0 ? revisions[index + 1]?.sha : undefined;
    void (async () => {
      try {
        const body = await getDocRevision(path, selected);
        let prevText: string | null = null;
        if (olderSha) {
          const prev = await getDocRevision(path, olderSha);
          prevText = prev.binary ? null : prev.text;
        }
        if (cancelled) return;
        setCurrent(body);
        setOlderText(prevText);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "无法读取这一版");
        }
      } finally {
        if (!cancelled) setLoadingBody(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, path, selected, revisions]);

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

  const canDiff = !current?.binary && current?.text != null && olderText != null;
  const showDiff = comparePrev && canDiff;

  const diffLines = useMemo(() => {
    if (!showDiff || current?.text == null) return [];
    return buildDocDiff(olderText ?? "", current.text);
  }, [showDiff, current, olderText]);

  if (!open || !path) return null;

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className="doc-history-modal doc-history-modal--frame"
        role="dialog"
        aria-modal="true"
        aria-labelledby="doc-history-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="doc-diff-header">
          <h3 id="doc-history-title">修订</h3>
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
          <aside className="doc-history-list" aria-label="版本列表">
            {loadingList ? (
              <p className="doc-diff-empty">正在读取…</p>
            ) : revisions.length === 0 ? (
              <p className="doc-diff-empty">还没有修订记录。</p>
            ) : (
              revisions.map((rev, i) => (
                <button
                  key={rev.sha}
                  type="button"
                  className={`doc-history-item${selected === rev.sha ? " is-active" : ""}`}
                  onClick={() => setSelected(rev.sha)}
                >
                  <span className="doc-history-item-time">
                    {i === 0 ? "现在" : formatRoutineRunTime(rev.committed_at)}
                  </span>
                  <span className="doc-history-item-msg">{rev.message}</span>
                </button>
              ))
            )}
          </aside>
          <section className="doc-history-pane">
            <div className="doc-history-pane-bar">
              <DocIconBtn
                label="和上一版比"
                active={comparePrev}
                aria-pressed={comparePrev}
                onClick={() => setComparePrev((on) => !on)}
              >
                <DiffIcon />
              </DocIconBtn>
            </div>
            <div
              className="doc-history-pane-body"
              aria-busy={loadingBody}
            >
              {error ? (
                <p className="doc-diff-empty">{error}</p>
              ) : !current && loadingBody ? (
                <p className="doc-diff-empty">正在打开这一版…</p>
              ) : current?.binary ? (
                <p className="doc-diff-empty">这一版是二进制，不能在这里预览。</p>
              ) : showDiff ? (
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
              ) : (
                <pre className="doc-history-text">{current?.text ?? ""}</pre>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
