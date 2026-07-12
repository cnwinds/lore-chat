import { useEffect } from "react";
import type { SourceRef } from "../../api";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";
import type { useKbFileSelection } from "./useKbFileSelection";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;
type Selection = ReturnType<typeof useKbFileSelection>;

export function useAppEscapeKey(
  doc: DocPreview,
  selection: Selection,
  snippetSource: Extract<SourceRef, { type: "search" }> | null,
  onCloseSnippet: () => void,
) {
  useEffect(() => {
    if (!doc.previewPath && !snippetSource && !selection.selectionMode) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (snippetSource !== null) {
        onCloseSnippet();
        return;
      }
      if (selection.selectionMode) {
        selection.setSelectionMode(false);
        selection.clearSelection();
        return;
      }
      if (!doc.previewPath) return;
      if (doc.docFocus) doc.exitDocFocus();
      else doc.requestCloseDocPreview();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    doc.previewPath,
    doc.docFocus,
    doc.docPinned,
    snippetSource,
    selection.selectionMode,
  ]);
}
