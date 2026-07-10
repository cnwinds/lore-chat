import { useEffect, useRef, useState } from "react";
import { getDoc, type DocContent } from "../api";
import { MarkdownContent } from "./MarkdownContent";

type Props = {
  path: string;
  highlightText?: string;
  mode?: "panel" | "page";
  onClose: () => void;
};

export function DocViewer({ path, highlightText, mode = "panel", onClose }: Props) {
  const [doc, setDoc] = useState<DocContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDoc(path)
      .then((d) => {
        if (!cancelled) setDoc(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

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

  return (
    <div className={`doc-viewer${mode === "panel" ? " doc-viewer-panel" : ""}`}>
      <header className="doc-viewer-header">
        {mode === "panel" ? (
          <button type="button" className="doc-close-btn" onClick={onClose} title="关闭">
            ×
          </button>
        ) : (
          <button type="button" className="doc-back-btn" onClick={onClose}>
            ← 对话
          </button>
        )}
        <div className="doc-viewer-title">
          <span className="doc-path">{path}</span>
          <h2>{title}</h2>
        </div>
      </header>
      <div className="doc-viewer-body" ref={bodyRef}>
        {loading && <div className="doc-muted">加载中…</div>}
        {error && <div className="doc-error">错误：{error}</div>}
        {doc && (
          <>
            {doc.meta && Object.keys(doc.meta).length > 0 && (
              <div className="doc-meta">
                {Object.entries(doc.meta).map(([k, v]) => (
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

