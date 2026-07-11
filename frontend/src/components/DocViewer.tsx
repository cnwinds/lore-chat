import { useEffect, useRef, useState } from "react";
import { getDoc, type DocContent } from "../api";
import { MarkdownContent } from "./MarkdownContent";

type DocWidth = "narrow" | "wide";
type DocMode = "panel" | "float" | "page";

type Props = {
  path: string;
  refreshKey?: number;
  highlightText?: string;
  mode?: DocMode;
  docWidth?: DocWidth;
  docFocus?: boolean;
  onClose: () => void;
  onPin?: () => void;
  onUnpin?: () => void;
  onToggleWidth?: () => void;
  onToggleFocus?: () => void;
  onOpenConversation?: (conversationId: string) => void;
};

function PinIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 17v5" />
      <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3.76z" />
    </svg>
  );
}

export function DocViewer({
  path,
  refreshKey = 0,
  highlightText,
  mode = "panel",
  docWidth = "narrow",
  docFocus = false,
  onClose,
  onPin,
  onUnpin,
  onToggleWidth,
  onToggleFocus,
  onOpenConversation,
}: Props) {
  const [doc, setDoc] = useState<DocContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDoc(null);
    getDoc(path)
      .then((d) => {
        if (!cancelled) setDoc(d);
      })
      .catch((e) => {
        if (!cancelled) {
          setDoc(null);
          setError(e instanceof Error ? e.message : "加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, refreshKey]);

  useEffect(() => {
    if (!highlightText || loading || !doc || !bodyRef.current) return;

    const container = bodyRef.current.querySelector(".doc-markdown");
    if (!container) return;

    const prev = container.querySelector(".highlight");
    prev?.classList.remove("highlight");

    const needle = highlightText.trim().slice(0, 120);
    if (!needle) return;

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node: Text | null = walker.nextNode() as Text | null;
    while (node) {
      const idx = node.textContent?.indexOf(needle) ?? -1;
      if (idx >= 0) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + needle.length);
        const mark = document.createElement("mark");
        mark.className = "highlight";
        try {
          range.surroundContents(mark);
          mark.scrollIntoView({ behavior: "smooth", block: "center" });
        } catch {
          mark.textContent = needle;
          node.parentNode?.insertBefore(mark, node);
          mark.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        break;
      }
      node = walker.nextNode() as Text | null;
    }
  }, [highlightText, loading, doc, path]);

  const title =
    (doc?.meta?.title as string | undefined) ||
    path.split("/").pop() ||
    path;

  const conversationId =
    typeof doc?.meta?.conversation_id === "string"
      ? doc.meta.conversation_id
      : null;

  return (
    <div
      className={`doc-viewer${mode === "panel" ? " doc-viewer-panel" : ""}${
        mode === "float" ? " doc-viewer-float" : ""
      }${docFocus ? " doc-viewer-focus" : ""}`}
    >
      <header className="doc-viewer-header">
        {mode === "panel" || mode === "float" ? (
          <button type="button" className="doc-close-btn" onClick={onClose} title="关闭">
            ×
          </button>
        ) : (
          <button type="button" className="doc-back-btn" onClick={onClose}>
            ← 对话
          </button>
        )}
        <div className="doc-viewer-title">
          {mode === "panel" && <span className="doc-path">{path}</span>}
          <h2>{title}</h2>
        </div>
        {(mode === "float" || mode === "panel") && (
          <div className="doc-viewer-actions">
            {mode === "float" && onPin && (
              <button
                type="button"
                className="doc-action-btn doc-pin-btn"
                onClick={onPin}
                title="固定到右侧栏"
              >
                <PinIcon />
              </button>
            )}
            {mode === "panel" && onUnpin && (
              <button
                type="button"
                className="doc-action-btn doc-pin-btn is-active"
                onClick={onUnpin}
                title="取消固定，回到浮窗预览"
              >
                <PinIcon filled />
              </button>
            )}
            {!docFocus && onToggleWidth && (
              <button
                type="button"
                className={`doc-action-btn${docWidth === "wide" ? " is-active" : ""}`}
                onClick={onToggleWidth}
                title={docWidth === "wide" ? "收窄阅读区" : "加宽阅读区"}
              >
                {docWidth === "wide" ? "窄栏" : "宽栏"}
              </button>
            )}
            {onToggleFocus && (
              <button
                type="button"
                className={`doc-action-btn${docFocus ? " is-active" : ""}`}
                onClick={onToggleFocus}
                title={docFocus ? "退出专注" : "专注阅读"}
              >
                {docFocus ? "退出专注" : "专注"}
              </button>
            )}
          </div>
        )}
      </header>
      <div className="doc-viewer-body" ref={bodyRef}>
        {loading && <div className="doc-muted">加载中…</div>}
        {error && <div className="doc-error">错误：{error}</div>}
        {doc && (
          <>
            {conversationId && onOpenConversation && (
              <div className="doc-conversation-link">
                <button
                  type="button"
                  className="doc-conversation-link-btn"
                  onClick={() => onOpenConversation(conversationId)}
                >
                  查看原始会话
                </button>
              </div>
            )}
            {doc.meta && Object.keys(doc.meta).length > 0 && (
              <div className="doc-meta">
                {Object.entries(doc.meta)
                  .filter(([k]) => k !== "conversation_id")
                  .map(([k, v]) => (
                  <span key={k} className="doc-meta-tag">
                    {k}: {Array.isArray(v) ? v.join(", ") : String(v)}
                  </span>
                ))}
              </div>
            )}
            <MarkdownContent className="markdown-body doc-markdown">
              {doc.body || "(空文档)"}
            </MarkdownContent>
          </>
        )}
      </div>
    </div>
  );
}
