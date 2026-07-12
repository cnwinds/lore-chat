import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;

export function buildDocViewerHandlers(
  doc: DocPreview,
  onOpenConversation: (id: string) => void,
) {
  return {
    onClose: doc.contextValue.closeDoc,
    onBindClose: doc.bindDocClose,
    onSaved: doc.refreshKb,
    onNavigationBlocked: (stayPath: string) => doc.setPreviewPath(stayPath),
    onToggleWidth: doc.toggleDocWidth,
    onToggleFocus: doc.toggleDocFocus,
    onOpenConversation,
    mergeReview: null,
    onMergeReviewChange: () => {},
    onMergeAccept: async () => {},
    onMergeRegenerate: async () => {},
    onMergeReject: async () => {},
  };
}
