import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DocDiffModal } from "./DocDiffModal";
import { type DocSelection } from "./DocLivePreview";
import { DocMergeReviewBar } from "./doc/DocMergeReviewBar";
import { DocViewerBody } from "./doc/DocViewerBody";
import { DocViewerHeader } from "./doc/DocViewerHeader";
import { useDocLoader } from "../hooks/doc/useDocLoader";
import {
  useDocDirtyPrompt,
  type MergeReviewInfo,
} from "../hooks/doc/useDocDirtyPrompt";
import { useDocHighlight } from "../hooks/doc/useDocHighlight";
import { useDocOutlineActive } from "../hooks/useDocOutlineActive";
import { isDocMarkdownDirty } from "../utils/docMarkdown";
import {
  jumpToOutlineInPreview,
  jumpToOutlineInSource,
  parseDocOutline,
  type OutlineItem,
} from "../utils/docOutline";
import type { DocMode, DocWidth, EditMode } from "../types/doc";
import { isReadOnlyPath } from "../utils/docReadOnly";
import { getStoredEditMode, setStoredEditMode } from "../utils/docStorage";

type Props = {
  path: string;
  refreshKey?: number;
  highlightText?: string;
  mode?: DocMode;
  docWidth?: DocWidth;
  docFocus?: boolean;
  onClose: () => void;
  /** 向父组件注册带 dirty 检查的关闭函数（用于点击浮层背景等外部关闭） */
  onBindClose?: (close: (() => void) | null) => void;
  onSaved?: (path: string) => void;
  onNavigationBlocked?: (stayPath: string) => void;
  onCloseRequest?: () => boolean;
  onPin?: () => void;
  onUnpin?: () => void;
  onToggleWidth?: () => void;
  onToggleFocus?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  mergeReview?: MergeReviewInfo | null;
  onMergeReviewChange?: (patch: Partial<{ userModified: boolean }>) => void;
  onMergeAccept?: () => void | Promise<void>;
  onMergeRegenerate?: () => void | Promise<void>;
  onMergeReject?: () => void | Promise<void>;
  onLocateInTree?: (path: string) => void;
};

export function DocViewer({
  path,
  refreshKey = 0,
  highlightText,
  mode = "panel",
  docWidth = "narrow",
  docFocus = false,
  onClose,
  onBindClose,
  onSaved,
  onNavigationBlocked,
  onCloseRequest,
  onPin,
  onUnpin,
  onToggleWidth,
  onToggleFocus,
  onOpenConversation,
  mergeReview = null,
  onMergeReviewChange,
  onMergeAccept,
  onMergeRegenerate,
  onMergeReject,
  onLocateInTree,
}: Props) {
  const [editMode, setEditMode] = useState<EditMode>(getStoredEditMode);
  const [selection, setSelection] = useState<DocSelection>({ start: 0, end: 0 });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mergeEditing, setMergeEditing] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const markdownSourceRef = useRef<HTMLTextAreaElement>(null);
  const mergeSourceRef = useRef<HTMLTextAreaElement>(null);

  const {
    doc,
    setDoc,
    body,
    setBody,
    savedBody,
    setSavedBody,
    loading,
    error,
    loadedPath,
    loadDoc,
    loadGenRef,
    lastRefreshKeyRef,
    userEditedRef,
    previewRemountKey,
    bumpPreviewRemount,
  } = useDocLoader({
    path,
    refreshKey,
    setSaveError,
    setSelection,
    setMergeEditing,
  });

  const readOnly = isReadOnlyPath(path);
  const {
    dirty,
    unsavedPrompt,
    setUnsavedPrompt,
    handleSave,
    handleMergeSave,
    handleConfirmSave,
    handleConfirmDiscard,
    handleClose,
    handleDiscard,
    cancelUnsavedPrompt,
  } = useDocDirtyPrompt({
    path,
    refreshKey,
    readOnly,
    onClose,
    onBindClose,
    onCloseRequest,
    onSaved,
    onNavigationBlocked,
    mergeReview,
    mergeEditing,
    onMergeReviewChange,
    doc,
    setDoc,
    body,
    setBody,
    savedBody,
    setSavedBody,
    loadedPath,
    loadDoc,
    loadGenRef,
    lastRefreshKeyRef,
    userEditedRef,
    bumpPreviewRemount,
    setSelection,
    saving,
    setSaving,
    setSaveError,
  });
  const outlineItems = useMemo(() => parseDocOutline(body), [body]);
  const outlineInSource =
    (mergeReview !== null && mergeEditing) || editMode === "markdown";
  const outlineActiveIndex = useDocOutlineActive({
    items: outlineItems,
    inSource: outlineInSource,
    scrollRootRef: bodyRef,
    sourceRef: markdownSourceRef,
    mergeSourceRef: mergeSourceRef,
    enabled: Boolean(doc) && !loading,
  });

  useEffect(() => {
    setOutlineOpen(false);
  }, [path, refreshKey]);

  const handleEditModeChange = (mode: EditMode) => {
    setEditMode(mode);
    setStoredEditMode(mode);
  };

  useEffect(() => {
    if (!mergeReview) {
      setMergeEditing(false);
    }
  }, [mergeReview]);

  useDocHighlight({
    bodyRef,
    highlightText,
    loading,
    doc,
    editMode,
    path,
    body,
  });

  const handleBodyChange = (nextBody: string, nextSelection?: DocSelection) => {
    userEditedRef.current = true;
    setBody(nextBody);
    if (nextSelection) setSelection(nextSelection);
  };

  /** 预览模式：Crepe 初始化后的二次序列化若仅表面差异，不记为用户编辑。 */
  const handlePreviewChange = useCallback(
    (nextBody: string) => {
      setBody(nextBody);
      if (userEditedRef.current) return;
      setSavedBody((saved) => {
        if (isDocMarkdownDirty(nextBody, saved)) {
          userEditedRef.current = true;
          return saved;
        }
        return nextBody;
      });
    },
    [setBody, setSavedBody, userEditedRef],
  );

  const handlePreviewStable = useCallback((md: string) => {
    if (userEditedRef.current) return;
    setBody(md);
    // 以 Crepe 序列化结果作为未编辑基线，避免 parse/serialize 与磁盘原文 purely cosmetic 差异
    setSavedBody(md);
  }, [setBody, setSavedBody, userEditedRef]);

  const handlePreviewUserEdit = useCallback(() => {
    userEditedRef.current = true;
  }, []);

  const handleOutlineJump = useCallback(
    (item: OutlineItem) => {
      const inSource =
        (mergeReview && mergeEditing) || editMode === "markdown";
      if (inSource) {
        const ta = mergeReview && mergeEditing
          ? mergeSourceRef.current
          : markdownSourceRef.current;
        jumpToOutlineInSource(ta, item.line);
      } else {
        jumpToOutlineInPreview(bodyRef.current, item);
      }
    },
    [editMode, mergeEditing, mergeReview],
  );

  return (
    <div
      className={`doc-viewer${mode === "panel" ? " doc-viewer-panel" : ""}${
        mode === "float" ? " doc-viewer-float" : ""
      }${docFocus ? " doc-viewer-focus" : ""}`}
    >
      <DocViewerHeader
        mode={mode}
        path={path}
        doc={doc}
        dirty={dirty}
        onClose={handleClose}
        editMode={editMode}
        onEditModeChange={handleEditModeChange}
        loading={loading}
        mergeEditing={mergeEditing}
        readOnly={readOnly}
        saving={saving}
        mergeReview={mergeReview}
        onDiscard={handleDiscard}
        onSave={handleSave}
        onMergeSave={async () => {
          await handleMergeSave();
        }}
        onViewDiff={() => setUnsavedPrompt("view")}
        outlineOpen={outlineOpen}
        onOutlineToggle={() => setOutlineOpen((v) => !v)}
        onOutlineClose={() => setOutlineOpen(false)}
        outlineItems={outlineItems}
        outlineActiveIndex={outlineActiveIndex}
        onOutlineJump={handleOutlineJump}
        docWidth={docWidth}
        docFocus={docFocus}
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
        onPin={onPin}
        onUnpin={onUnpin}
        onOpenConversation={onOpenConversation}
        onMergeEditingToggle={() => setMergeEditing((v) => !v)}
        onLocateInTree={onLocateInTree}
      />
      <DocViewerBody
        bodyRef={bodyRef}
        loading={loading}
        error={error}
        saveError={saveError}
        readOnly={readOnly}
        doc={doc}
        mergeReview={mergeReview}
        mergeEditing={mergeEditing}
        mergeSourceRef={mergeSourceRef}
        editMode={editMode}
        body={body}
        onBodyChange={handleBodyChange}
        onPreviewChange={handlePreviewChange}
        loadedPath={loadedPath}
        refreshKey={refreshKey}
        previewRemountKey={previewRemountKey}
        onPreviewStable={handlePreviewStable}
        onPreviewUserEdit={handlePreviewUserEdit}
        markdownSourceRef={markdownSourceRef}
        selection={selection}
        onSelectionChange={setSelection}
      />
      {mergeReview && (
        <DocMergeReviewBar
          mergeReview={mergeReview}
          onMergeAccept={onMergeAccept}
          onMergeRegenerate={onMergeRegenerate}
          onMergeReject={onMergeReject}
        />
      )}
      <DocDiffModal
        open={unsavedPrompt !== null}
        variant={unsavedPrompt === "view" ? "view" : "confirm"}
        hint={
          unsavedPrompt === "navigate"
            ? "切换文档前请处理未保存的修改。"
            : unsavedPrompt === "reload"
              ? "重新加载将丢失未保存的修改。"
              : unsavedPrompt === "close"
                ? "关闭前请处理未保存的修改。"
                : undefined
        }
        saveLabel={
          unsavedPrompt === "navigate"
            ? "保存并切换"
            : unsavedPrompt === "reload"
              ? "保存并重新加载"
              : unsavedPrompt === "close"
                ? "保存并关闭"
                : undefined
        }
        saved={savedBody}
        current={body}
        saving={saving}
        onClose={() => {
          if (unsavedPrompt === "view") setUnsavedPrompt(null);
          else cancelUnsavedPrompt();
        }}
        onDiscard={
          !readOnly
            ? () => {
                if (unsavedPrompt === "view") handleDiscard();
                else handleConfirmDiscard();
              }
            : undefined
        }
        onSave={
          !readOnly &&
          (unsavedPrompt === "view" ? dirty : unsavedPrompt !== null)
            ? () => {
                if (unsavedPrompt === "view") {
                  void handleSave().then((ok) => {
                    if (ok) setUnsavedPrompt(null);
                  });
                } else {
                  void handleConfirmSave();
                }
              }
            : undefined
        }
      />
    </div>
  );
}
