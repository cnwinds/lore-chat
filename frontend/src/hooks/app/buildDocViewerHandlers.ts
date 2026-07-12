import type { useDocPreviewLayout } from "./useDocPreviewLayout";
import type { useMergeReviewSession } from "./useMergeReviewSession";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;
type Merge = ReturnType<typeof useMergeReviewSession>;

export function buildDocViewerHandlers(
  doc: DocPreview,
  merge: Merge,
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
    mergeReview: merge.activeMergeReview,
    onMergeReviewChange: (patch: Partial<{ userModified: boolean }>) =>
      merge.setMergeReview((prev) => (prev ? { ...prev, ...patch } : prev)),
    onMergeAccept: merge.handleMergeAccept,
    onMergeRegenerate: merge.handleMergeRegenerate,
    onMergeReject: merge.handleMergeReject,
  };
}
