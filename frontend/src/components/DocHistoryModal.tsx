import { useEffect, useRef, useState } from "react";
import {
  getDocRevision,
  listDocRevisions,
  type DocRevisionBody,
  type DocRevisionInfo,
} from "../api";
import { formatRoutineRunTime } from "../utils/displayTime";
import { DiffIcon, DocIconBtn } from "./DocToolbarIcons";
import { DocRevisionCompareView } from "./doc/DocRevisionCompareView";

type Props = {
  open: boolean;
  path: string | null;
  previewText?: string | null;
  onClose: () => void;
};

function previewAsBody(path: string, text: string): DocRevisionBody {
  return {
    path,
    sha: "",
    short_sha: "",
    message: "",
    committed_at: "",
    text,
    binary: false,
    size: text.length,
  };
}

export function DocHistoryModal({
  open,
  path,
  previewText = null,
  onClose,
}: Props) {
  const [revisions, setRevisions] = useState<DocRevisionInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<DocRevisionBody | null>(null);
  const [olderText, setOlderText] = useState<string | null>(null);
  const [comparePrev, setComparePrev] = useState(true);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingBody, setLoadingBody] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyCacheRef = useRef<Record<string, DocRevisionBody>>({});
  const previewRef = useRef(previewText);
  previewRef.current = previewText;

  useEffect(() => {
    if (!open || !path) return;
    let cancelled = false;
    bodyCacheRef.current = {};
    setLoadingList(true);
    setError(null);
    setRevisions([]);
    setSelected(null);
    setOlderText(null);
    setComparePrev(true);
    const preview = previewRef.current;
    if (preview != null) {
      setCurrent(previewAsBody(path, preview));
      setLoadingBody(false);
    } else {
      setCurrent(null);
      setLoadingBody(true);
    }
    void listDocRevisions(path)
      .then((data) => {
        if (cancelled) return;
        const bodies = data.bodies ?? {};
        bodyCacheRef.current = { ...bodies };
        setRevisions(data.revisions);
        const first = data.revisions[0];
        setSelected(first?.sha ?? null);
        if (first && bodies[first.sha]) {
          setCurrent(bodies[first.sha]);
          const second = data.revisions[1];
          const prev = second ? bodies[second.sha] : undefined;
          if (!second) setOlderText(null);
          else if (prev) setOlderText(prev.binary ? null : prev.text);
          setLoadingBody(false);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "无法读取修订");
          setLoadingList(false);
          setLoadingBody(false);
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
    const cache = bodyCacheRef.current;
    const index = revisions.findIndex((r) => r.sha === selected);
    const olderSha = index >= 0 ? revisions[index + 1]?.sha : undefined;
    const cached = cache[selected];
    const cachedOlder = olderSha ? cache[olderSha] : undefined;

    if (cached) {
      setCurrent(cached);
      setLoadingBody(false);
      if (!olderSha) {
        setOlderText(null);
        return;
      }
      if (cachedOlder) {
        setOlderText(cachedOlder.binary ? null : cachedOlder.text);
        return;
      }
    } else {
      setLoadingBody(true);
    }

    void (async () => {
      try {
        const body = cached ?? (await getDocRevision(path, selected));
        if (cancelled) return;
        cache[body.sha] = body;
        cache[selected] = body;
        setCurrent(body);
        setLoadingBody(false);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "无法读取这一版");
          setLoadingBody(false);
        }
        return;
      }
      if (!olderSha) {
        if (!cancelled) setOlderText(null);
        return;
      }
      try {
        const prev = cachedOlder ?? (await getDocRevision(path, olderSha));
        if (cancelled) return;
        cache[prev.sha] = prev;
        cache[olderSha] = prev;
        setOlderText(prev.binary ? null : prev.text);
      } catch {
        if (!cancelled) setOlderText(null);
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

  if (!open || !path) return null;

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className={`doc-history-modal doc-history-modal--frame${showDiff ? " doc-history-modal--compare" : ""}`}
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
            <div className="doc-history-pane-body" aria-busy={loadingBody}>
              {error ? (
                <p className="doc-diff-empty">{error}</p>
              ) : !current && loadingBody ? (
                <p className="doc-diff-empty">正在打开这一版…</p>
              ) : current?.binary ? (
                <p className="doc-diff-empty">这一版是二进制，不能在这里预览。</p>
              ) : showDiff && current.text != null && olderText != null ? (
                <DocRevisionCompareView
                  older={olderText}
                  newer={current.text}
                />
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
