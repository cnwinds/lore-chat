import type { DocPane } from "../../types/doc";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;

export function buildDocViewerHandlers(
  doc: DocPreview,
  pane: DocPane,
  onOpenConversation: (id: string) => void,
) {
  const shared = {
    // 本栏刚写完，勿 bump 本栏 refreshKey（否则会 loadDoc remount，丢滚动/光标）
    onSaved: (path: string) => doc.refreshKb(path, { except: pane }),
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
