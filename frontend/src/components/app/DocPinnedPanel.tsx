import { DocViewer } from "../DocViewer";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";
import type { DocWidth } from "../../types/doc";

type Props = {
  path: string;
  refreshKey: number;
  highlightText?: string;
  docWidth: DocWidth;
  docFocus: boolean;
  onClose: () => void;
  onBindClose: (handler: (() => void) | null) => void;
  onSaved: (path: string) => void;
  onNavigationBlocked: (stayPath: string) => void;
  onUnpin: () => void;
  onToggleWidth: () => void;
  onToggleFocus: () => void;
  onOpenConversation: (conversationId: string) => void;
  mergeReview: MergeReviewInfo | null;
  onMergeReviewChange: (patch: Partial<{ userModified: boolean }>) => void;
  onMergeAccept: () => void | Promise<void>;
  onMergeRegenerate: () => void | Promise<void>;
  onMergeReject: () => void | Promise<void>;
};

export function DocPinnedPanel({
  path,
  refreshKey,
  highlightText,
  docWidth,
  docFocus,
  onClose,
  onBindClose,
  onSaved,
  onNavigationBlocked,
  onUnpin,
  onToggleWidth,
  onToggleFocus,
  onOpenConversation,
  mergeReview,
  onMergeReviewChange,
  onMergeAccept,
  onMergeRegenerate,
  onMergeReject,
}: Props) {
  return (
    <aside
      className={
        docFocus ? "doc-panel" : `doc-panel doc-panel--${docWidth}`
      }
    >
      <DocViewer
        path={path}
        refreshKey={refreshKey}
        highlightText={highlightText}
        mode="panel"
        docWidth={docWidth}
        docFocus={docFocus}
        onClose={onClose}
        onBindClose={onBindClose}
        onSaved={onSaved}
        onNavigationBlocked={onNavigationBlocked}
        onUnpin={onUnpin}
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
        onOpenConversation={onOpenConversation}
        mergeReview={mergeReview}
        onMergeReviewChange={onMergeReviewChange}
        onMergeAccept={onMergeAccept}
        onMergeRegenerate={onMergeRegenerate}
        onMergeReject={onMergeReject}
      />
    </aside>
  );
}
