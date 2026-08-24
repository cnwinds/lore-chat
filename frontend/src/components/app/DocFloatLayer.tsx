import { DocViewer } from "../DocViewer";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";
import type { DocWidth } from "../../types/doc";

type Props = {
  path: string;
  refreshKey: number;
  highlightText?: string;
  docWidth: DocWidth;
  docFocus: boolean;
  showBackdrop: boolean;
  onRequestClose: () => void;
  onClose: () => void;
  onBindClose: (handler: (() => void) | null) => void;
  onSaved: (path: string) => void;
  onNavigationBlocked: (stayPath: string) => void;
  onPin: () => void;
  onToggleWidth: () => void;
  onToggleFocus: () => void;
  onOpenConversation: (conversationId: string) => void;
  mergeReview: MergeReviewInfo | null;
  onMergeReviewChange: (patch: Partial<{ userModified: boolean }>) => void;
  onMergeAccept: () => void | Promise<void>;
  onMergeRegenerate: () => void | Promise<void>;
  onMergeReject: () => void | Promise<void>;
  onLocateInTree?: (path: string) => void;
  onShareDoc?: (path: string, title: string) => void;
};

export function DocFloatLayer({
  path,
  refreshKey,
  highlightText,
  docWidth,
  docFocus,
  showBackdrop,
  onRequestClose,
  onClose,
  onBindClose,
  onSaved,
  onNavigationBlocked,
  onPin,
  onToggleWidth,
  onToggleFocus,
  onOpenConversation,
  mergeReview,
  onMergeReviewChange,
  onMergeAccept,
  onMergeRegenerate,
  onMergeReject,
  onLocateInTree,
  onShareDoc,
}: Props) {
  return (
    <>
      {showBackdrop && (
        <div
          className="doc-float-backdrop"
          aria-hidden
          onClick={onRequestClose}
        />
      )}
      <div
        className="doc-float-panel"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <DocViewer
          path={path}
          refreshKey={refreshKey}
          highlightText={highlightText}
          mode="float"
          docWidth={docWidth}
          docFocus={docFocus}
          onClose={onClose}
          onBindClose={onBindClose}
          onSaved={onSaved}
          onNavigationBlocked={onNavigationBlocked}
          onPin={onPin}
          onToggleWidth={onToggleWidth}
          onToggleFocus={onToggleFocus}
          onOpenConversation={onOpenConversation}
          mergeReview={mergeReview}
          onMergeReviewChange={onMergeReviewChange}
          onMergeAccept={onMergeAccept}
          onMergeRegenerate={onMergeRegenerate}
          onMergeReject={onMergeReject}
          onLocateInTree={onLocateInTree}
          onShareDoc={onShareDoc}
        />
      </div>
    </>
  );
}
