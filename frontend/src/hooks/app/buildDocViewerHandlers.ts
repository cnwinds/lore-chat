import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;
type DocPane = "float" | "pinned";

export function buildDocViewerHandlers(
  doc: DocPreview,
  pane: DocPane,
  onOpenConversation: (id: string) => void,
) {
  const shared = {
    onSaved: doc.refreshKb,
    onOpenConversation,
    mergeReview: null,
    onMergeReviewChange: () => {},
    onMergeAccept: async () => {},
    onMergeRegenerate: async () => {},
    onMergeReject: async () => {},
  };

  if (pane === "float") {
    return {
      ...shared,
      onClose: doc.closeFloatPreview,
      onBindClose: doc.bindFloatClose,
      onNavigationBlocked: (stayPath: string) => doc.setFloatPath(stayPath),
      onToggleWidth: doc.toggleFloatWidth,
      onToggleFocus: doc.toggleFloatFocus,
    };
  }

  return {
    ...shared,
    onClose: doc.closePinnedPreview,
    onBindClose: doc.bindPinnedClose,
    onNavigationBlocked: (stayPath: string) => doc.setPinnedPath(stayPath),
    onToggleWidth: doc.togglePinnedWidth,
    onToggleFocus: doc.togglePinnedFocus,
  };
}
