import { useEffect, useMemo, useState } from "react";
import {
  getContextStats,
  type ContextStatsSegment,
} from "../../api";
import { compactTokenCount } from "../../utils/chatMessageFormat";
import { segmentColor } from "./contextSegmentColors";

type Props = {
  open: boolean;
  conversationId: string;
  initialKey: string | null;
  onClose: () => void;
};

/** 上下文构成检查器：全文（按注入顺序、分段配色）或单段查看。 */
export function ContextInspectorModal({
  open,
  conversationId,
  initialKey,
  onClose,
}: Props) {
  const [segments, setSegments] = useState<ContextStatsSegment[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<string>("all");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSegments(null);
    setTab(initialKey || "all");
    getContextStats(conversationId, { includeTexts: true })
      .then((stats) => {
        if (!cancelled) setSegments(stats.segments);
      })
      .catch(() => {
        if (!cancelled) setError("注入文本加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId, initialKey, open]);

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

  const filled = useMemo(
    () => (segments ?? []).filter((seg) => (seg.text || "").trim().length > 0),
    [segments],
  );
  const emptyLabels = useMemo(
    () =>
      (segments ?? [])
        .filter((seg) => (seg.text || "").trim().length === 0)
        .map((seg) => seg.label),
    [segments],
  );
  const used = useMemo(
    () => (segments ?? []).reduce((sum, seg) => sum + seg.tokens, 0),
    [segments],
  );

  if (!open) return null;

  const active =
    tab === "all" ? null : (segments ?? []).find((seg) => seg.key === tab);
  const shown: ContextStatsSegment[] = active ? [active] : filled;
  const visionOnly =
    active &&
    active.tokens > 0 &&
    !(active.text || "").trim() &&
    active.key === "attachments";

  function copyCurrent() {
    const text = shown
      .map((seg) => `【${seg.label}】\n${(seg.text || "").trim()}`)
      .join("\n\n");
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="ctxinspector-overlay" role="presentation" onClick={onClose}>
      <div
        className="ctxinspector"
        role="dialog"
        aria-modal="true"
        aria-label="上下文构成"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ctxinspector-head">
          <h3>上下文构成</h3>
          <button
            type="button"
            className="ctxinspector-copy"
            onClick={copyCurrent}
            disabled={loading || !shown.length}
          >
            {copied ? "已复制" : "复制"}
          </button>
          <button
            type="button"
            className="ctxinspector-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </header>
        <nav className="ctxinspector-tabs" aria-label="分段切换">
          <button
            type="button"
            className={`ctxinspector-tab${tab === "all" ? " is-active" : ""}`}
            aria-pressed={tab === "all"}
            onClick={() => setTab("all")}
          >
            全文
          </button>
          {filled.map((seg) => (
            <button
              key={seg.key}
              type="button"
              className={`ctxinspector-tab${tab === seg.key ? " is-active" : ""}`}
              aria-pressed={tab === seg.key}
              onClick={() => setTab(seg.key)}
            >
              <span
                className="ctxstats-dot"
                style={{ background: segmentColor(seg.key) }}
              />
              {seg.label}
            </button>
          ))}
        </nav>
        <div className="ctxinspector-body" aria-busy={loading}>
          {loading ? (
            <p className="ctxinspector-empty">正在读取注入文本…</p>
          ) : error ? (
            <p className="ctxinspector-empty">{error}</p>
          ) : visionOnly ? (
            <p className="ctxinspector-empty">
              识图 / 视频附件按常量估算，没有可查看的文本。
            </p>
          ) : shown.length ? (
            shown.map((seg) => (
              <section key={seg.key} className="ctxinspector-section">
                <header className="ctxinspector-section-head">
                  <span
                    className="ctxstats-dot"
                    style={{ background: segmentColor(seg.key) }}
                  />
                  <span className="ctxinspector-section-label">
                    {seg.label}
                  </span>
                  <span className="ctxinspector-section-meta">
                    {compactTokenCount(seg.tokens)} tokens
                    {used > 0 && seg.tokens > 0
                      ? ` · ${((seg.tokens / used) * 100).toFixed(1)}%`
                      : ""}
                  </span>
                </header>
                <pre
                  className="ctxinspector-text"
                  style={{ borderColor: segmentColor(seg.key) }}
                >
                  {(seg.text || "").trim() || "本轮未注入"}
                </pre>
              </section>
            ))
          ) : (
            <p className="ctxinspector-empty">本轮未注入任何分段内容。</p>
          )}
          {tab === "all" && !loading && emptyLabels.length ? (
            <p className="ctxinspector-skipped">
              {`${emptyLabels.join("、")}：本轮未注入`}
            </p>
          ) : null}
        </div>
        <footer className="ctxinspector-foot">
          分项按下一轮实际注入文本估算，可整体复制对照。
        </footer>
      </div>
    </div>
  );
}
