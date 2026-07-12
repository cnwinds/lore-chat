import { useEffect } from "react";
import type { SourceRef } from "../../api";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;

export function useAppEscapeKey(
  doc: DocPreview,
  snippetSource: Extract<SourceRef, { type: "search" }> | null,
  onCloseSnippet: () => void,
) {
  useEffect(() => {
    if (!doc.previewPath && !snippetSource) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (snippetSource !== null) {
        onCloseSnippet();
        return;
      }
      if (!doc.previewPath) return;
      if (doc.docFocus) doc.exitDocFocus();
      else doc.requestCloseDocPreview();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [doc.previewPath, doc.docFocus, doc.docPinned, snippetSource]);
}
