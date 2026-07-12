import { useEffect, type RefObject } from "react";
import type { DocContent } from "../../api";
import type { EditMode } from "../../types/doc";

type UseDocHighlightOptions = {
  bodyRef: RefObject<HTMLDivElement | null>;
  highlightText?: string;
  loading: boolean;
  doc: DocContent | null;
  editMode: EditMode;
  path: string;
  body: string;
};

export function useDocHighlight({
  bodyRef,
  highlightText,
  loading,
  doc,
  editMode,
  path,
  body,
}: UseDocHighlightOptions): void {
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
  }, [highlightText, loading, doc, path, body, editMode, bodyRef]);
}
