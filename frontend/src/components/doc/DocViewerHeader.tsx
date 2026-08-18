import type { DocContent } from "../../api";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";
import type { DocMode, DocWidth, EditMode } from "../../types/doc";
import { DocMetaPopover } from "../DocMetaPopover";
import { DocOutlineMenu } from "../DocOutlineMenu";
import { DocOverflowMenu, type OverflowItem } from "../DocOverflowMenu";
import {
  DocIconBtn,
  DiffIcon,
  DiscardIcon,
  FocusEnterIcon,
  FocusExitIcon,
  MarkdownIcon,
  PinIcon,
  PreviewIcon,
  SaveIcon,
  WidthExpandIcon,
  WidthNarrowIcon,
} from "../DocToolbarIcons";
import { type OutlineItem } from "../../utils/docOutline";
import { useDemoCapability } from "../../hooks/useDemoCapability";

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
}: Props) {
  const { canWrite } = useDemoCapability();
  const locked = readOnly || !canWrite;
  const conversationId =
    typeof doc?.meta?.conversation_id === "string"
      ? doc.meta.conversation_id
      : null;

  const overflowItems: OverflowItem[] = [
    ...(dirty && !locked
      ? [
          {
            id: "view-diff",
            label: "查看变更",
            icon: "diff" as const,
            onClick: onViewDiff,
          },
        ]
      : []),
    ...(mergeReview && canWrite
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
    !locked &&
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
      </div>
      <div className="doc-viewer-toolbar">
        {doc?.meta && <DocMetaPopover meta={doc.meta} />}
        <div className="doc-mode-toggle" role="group" aria-label="编辑模式">
          <DocIconBtn
            className="doc-mode-toggle-btn"
            label="预览模式"
            active={editMode === "preview"}
            onClick={() => onEditModeChange("preview")}
            disabled={loading || mergeEditing}
          >
            <PreviewIcon />
          </DocIconBtn>
          <DocIconBtn
            className="doc-mode-toggle-btn"
            label="Markdown 源码"
            active={editMode === "markdown"}
            onClick={() => onEditModeChange("markdown")}
            disabled={loading || mergeEditing}
          >
            <MarkdownIcon />
          </DocIconBtn>
        </div>
        {!locked && (
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
        {showLayoutActions && (
          <>
            <span className="doc-toolbar-divider" aria-hidden />
            {doc && (
              <DocOutlineMenu
                open={outlineOpen}
                onToggle={onOutlineToggle}
                onClose={onOutlineClose}
                items={outlineItems}
                activeIndex={outlineActiveIndex}
                onJump={onOutlineJump}
                disabled={loading}
              />
            )}
            {!docFocus && onToggleWidth && (
              <DocIconBtn
                label={docWidth === "wide" ? "收窄阅读区" : "加宽阅读区"}
                active={docWidth === "wide"}
                onClick={onToggleWidth}
              >
                {docWidth === "wide" ? <WidthNarrowIcon /> : <WidthExpandIcon />}
              </DocIconBtn>
            )}
            {onToggleFocus && (
              <DocIconBtn
                label={docFocus ? "退出专注" : "专注阅读"}
                active={docFocus}
                onClick={onToggleFocus}
              >
                {docFocus ? <FocusExitIcon /> : <FocusEnterIcon />}
              </DocIconBtn>
            )}
            <DocOverflowMenu items={overflowItems} disabled={loading} />
            {mode === "float" && onPin && (
              <DocIconBtn label="固定到右侧栏" onClick={onPin}>
                <PinIcon />
              </DocIconBtn>
            )}
            {mode === "panel" && onUnpin && (
              <DocIconBtn label="取消固定，回到浮窗预览" active onClick={onUnpin}>
                <PinIcon filled />
              </DocIconBtn>
            )}
          </>
        )}
        {mode === "page" && doc && (
          <>
            <span className="doc-toolbar-divider" aria-hidden />
            <DocOutlineMenu
              open={outlineOpen}
              onToggle={onOutlineToggle}
              onClose={onOutlineClose}
              items={outlineItems}
              activeIndex={outlineActiveIndex}
              onJump={onOutlineJump}
              disabled={loading}
            />
            <DocOverflowMenu items={overflowItems} disabled={loading} />
          </>
        )}
      </div>
    </header>
  );
}
