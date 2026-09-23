import type { DocContent } from "../../api";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";
import type { DocMode, DocWidth, EditMode } from "../../types/doc";
import { DocMetaPopover } from "../DocMetaPopover";
import { DocOutlineMenu } from "../DocOutlineMenu";
import { DocOverflowMenu, type OverflowItem } from "../DocOverflowMenu";
import {
  DocIconBtn,
  AlertIcon,
  DiffIcon,
  HistoryIcon,
  DiscardIcon,
  MarkdownIcon,
  PinIcon,
  QuietReadingIcon,
  SaveIcon,
  ShareIcon,
} from "../DocToolbarIcons";
import { type OutlineItem } from "../../utils/docOutline";

type Props = {
  mode: DocMode;
  path: string;
  doc: DocContent | null;
  dirty: boolean;
  onClose: () => void;
  editMode: EditMode;
  onEditModeChange: (mode: EditMode) => void;
  loading: boolean;
  mergeEditing: boolean;
  readOnly: boolean;
  saving: boolean;
  mergeReview: MergeReviewInfo | null;
  onDiscard: () => void | Promise<void>;
  onSave: () => void | Promise<boolean | void>;
  onMergeSave: () => void | Promise<void>;
  onViewDiff: () => void;
  onViewHistory: () => void;
  outlineOpen: boolean;
  onOutlineToggle: () => void;
  onOutlineClose: () => void;
  outlineItems: OutlineItem[];
  outlineActiveIndex: number;
  onOutlineJump: (item: OutlineItem) => void;
  docWidth: DocWidth;
  docFocus: boolean;
  onToggleWidth?: () => void;
  onToggleFocus?: () => void;
  onPin?: () => void;
  onUnpin?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onMergeEditingToggle: () => void;
  onLocateInTree?: (path: string) => void;
  onShareDoc?: (path: string, title: string) => void;
  /** 戒律官方更新有待确认冲突：工具栏亮红色警示，点击打开合并界面。 */
  preceptsAlert?: { conflicts: number; onReview: () => void } | null;
};

export function DocViewerHeader({
  mode,
  path,
  doc,
  dirty,
  onClose,
  editMode,
  onEditModeChange,
  loading,
  mergeEditing,
  readOnly,
  saving,
  mergeReview,
  onDiscard,
  onSave,
  onMergeSave,
  onViewDiff,
  onViewHistory,
  outlineOpen,
  onOutlineToggle,
  onOutlineClose,
  outlineItems,
  outlineActiveIndex,
  onOutlineJump,
  docWidth,
  docFocus,
  onToggleWidth,
  onToggleFocus,
  onPin,
  onUnpin,
  onOpenConversation,
  onMergeEditingToggle,
  onLocateInTree,
  onShareDoc,
  preceptsAlert,
}: Props) {
  const conversationId =
    typeof doc?.meta?.conversation_id === "string"
      ? doc.meta.conversation_id
      : null;

  const overflowItems: OverflowItem[] = [
    ...(dirty && !readOnly
      ? [
          {
            id: "view-diff",
            label: "查看变更",
            icon: "diff" as const,
            onClick: onViewDiff,
          },
        ]
      : []),
    ...(mergeReview
      ? [
          {
            id: "merge-edit",
            label: mergeEditing ? "结束手工编辑" : "手工编辑合并结果",
            icon: "edit" as const,
            active: mergeEditing,
            onClick: onMergeEditingToggle,
          },
        ]
      : []),
    ...(conversationId && onOpenConversation
      ? [
          {
            id: "conversation",
            label: "查看原始会话",
            icon: "chat" as const,
            onClick: () => onOpenConversation(conversationId),
          },
        ]
      : []),
  ];

  const showLayoutActions = mode === "float" || mode === "panel";
  const canSave =
    !readOnly &&
    (mergeReview && mergeEditing ? !saving && !loading : dirty && !saving && !loading);

  return (
    <header className="doc-viewer-header">
      {mode === "panel" || mode === "float" ? (
        <button
          type="button"
          className="doc-close-btn"
          onClick={onClose}
          title="关闭"
        >
          ×
        </button>
      ) : (
        <button type="button" className="doc-back-btn" onClick={onClose}>
          ← 对话
        </button>
      )}
      <div className="doc-viewer-title">
        {onLocateInTree ? (
          <button
            type="button"
            className="doc-path doc-path-btn"
            title={`在知识库中定位：${path}`}
            onClick={() => onLocateInTree(path)}
          >
            {path}
            {dirty && (
              <span
                className="doc-dirty-dot"
                title="有未保存的修改"
                aria-label="有未保存的修改"
              />
            )}
          </button>
        ) : (
          <span className="doc-path" title={path}>
            {path}
            {dirty && (
              <span
                className="doc-dirty-dot"
                title="有未保存的修改"
                aria-label="有未保存的修改"
              />
            )}
          </span>
        )}
      </div>
      <div className="doc-viewer-toolbar">
        <DocIconBtn
          label={editMode === "markdown" ? "退出开发" : "开发"}
          active={editMode === "markdown"}
          onClick={() =>
            onEditModeChange(editMode === "markdown" ? "preview" : "markdown")
          }
          disabled={loading || mergeEditing}
        >
          <MarkdownIcon />
        </DocIconBtn>
        {!readOnly && (
          <>
            {dirty && (
              <DocIconBtn
                label="放弃未保存的修改"
                onClick={() => void onDiscard()}
                disabled={saving || loading}
              >
                <DiscardIcon />
              </DocIconBtn>
            )}
            <DocIconBtn
              label={saving ? "保存中…" : "保存 (Ctrl+S)"}
              active={dirty}
              muted={!dirty && !(mergeReview && mergeEditing)}
              disabled={!canSave}
              onClick={() =>
                void (mergeReview && mergeEditing ? onMergeSave() : onSave())
              }
            >
              <SaveIcon />
            </DocIconBtn>
            {dirty && (
              <DocIconBtn
                label="查看变更"
                onClick={onViewDiff}
                disabled={loading}
              >
                <DiffIcon />
              </DocIconBtn>
            )}
          </>
        )}
        {preceptsAlert ? (
          <DocIconBtn
            label={`戒律有官方更新待确认（${preceptsAlert.conflicts} 处冲突，点击合并）`}
            className="doc-icon-btn--alert"
            onClick={preceptsAlert.onReview}
          >
            <AlertIcon />
            <span className="doc-icon-btn-dot" aria-hidden />
          </DocIconBtn>
        ) : null}
        <DocIconBtn
          label="修订"
          onClick={onViewHistory}
          disabled={loading}
        >
          <HistoryIcon />
        </DocIconBtn>
        {(showLayoutActions || mode === "page") && (
          <>
            <span className="doc-toolbar-divider" aria-hidden />
            {doc && (
              <div className="doc-toolbar-cluster" role="group" aria-label="文档查阅">
                {doc.meta ? <DocMetaPopover meta={doc.meta} /> : null}
                <DocOutlineMenu
                  open={outlineOpen}
                  onToggle={onOutlineToggle}
                  onClose={onOutlineClose}
                  items={outlineItems}
                  activeIndex={outlineActiveIndex}
                  onJump={onOutlineJump}
                  disabled={loading}
                />
              </div>
            )}
            {onShareDoc ? (
              <DocIconBtn
                label="分享"
                disabled={loading}
                onClick={() =>
                  onShareDoc(path, path.split("/").pop() || path)
                }
              >
                <ShareIcon />
              </DocIconBtn>
            ) : null}
            {showLayoutActions && (
              <>
                {onToggleFocus && (
                  <DocIconBtn
                    className="doc-toolbar-wide-only"
                    label="沉静阅读"
                    active={docFocus}
                    aria-pressed={docFocus}
                    onClick={() => {
                      if (docFocus) {
                        onToggleFocus();
                        if (docWidth !== "wide") onToggleWidth?.();
                      } else {
                        onToggleFocus();
                      }
                    }}
                  >
                    <QuietReadingIcon />
                  </DocIconBtn>
                )}
                <DocOverflowMenu items={overflowItems} disabled={loading} />
                {mode === "float" && onPin && (
                  <DocIconBtn label="固定到右侧栏" onClick={onPin}>
                    <PinIcon />
                  </DocIconBtn>
                )}
                {mode === "panel" && onUnpin && (
                  <DocIconBtn
                    label="取消固定，回到浮窗预览"
                    active
                    onClick={onUnpin}
                  >
                    <PinIcon filled />
                  </DocIconBtn>
                )}
              </>
            )}
            {mode === "page" && (
              <DocOverflowMenu items={overflowItems} disabled={loading} />
            )}
          </>
        )}
      </div>
    </header>
  );
}
