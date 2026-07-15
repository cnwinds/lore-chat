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
    const hasPreview = Boolean(doc.floatPath || doc.pinnedPath);
    if (!hasPreview && !snippetSource) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (snippetSource !== null) {
        onCloseSnippet();
        return;
      }
      if (doc.floatFocus) {
        doc.exitFloatFocus();
        return;
      }
      if (doc.pinnedFocus) {
        doc.exitPinnedFocus();
        return;
      }
      if (doc.floatPath) {
        doc.requestCloseFloatPreview();
        return;
      }
      if (doc.pinnedPath) {
        doc.requestClosePinnedPreview();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    doc.floatPath,
    doc.pinnedPath,
    doc.floatFocus,
    doc.pinnedFocus,
    snippetSource,
  ]);
}
