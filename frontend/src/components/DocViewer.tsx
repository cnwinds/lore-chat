import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getMergeSession, saveDoc } from "../api";
import { DocDiffModal } from "./DocDiffModal";
import { DocLivePreview, type DocSelection } from "./DocLivePreview";
import { DocMarkdownSource } from "./DocMarkdownSource";
import { DocMetaPopover } from "./DocMetaPopover";
import { DocOutlineMenu } from "./DocOutlineMenu";
import { DocOverflowMenu } from "./DocOverflowMenu";
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
} from "./DocToolbarIcons";
import { useDocLoader } from "../hooks/doc/useDocLoader";
import {
  useDocDirtyPrompt,
  type MergeReviewInfo,
} from "../hooks/doc/useDocDirtyPrompt";
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
}: Props) {
  const [editMode, setEditMode] = useState<EditMode>(getStoredEditMode);
  const [selection, setSelection] = useState<DocSelection>({ start: 0, end: 0 });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mergeEditing, setMergeEditing] = useState(false);
  const [mergeBusyAction, setMergeBusyAction] = useState<
    "reject" | "regenerate" | "accept" | null
  >(null);
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
      setMergeBusyAction(null);
    }
  }, [mergeReview]);

  const handleBodyChange = (nextBody: string, nextSelection?: DocSelection) => {
    userEditedRef.current = true;
    setBody(nextBody);
    if (nextSelection) setSelection(nextSelection);
  };

  const handlePreviewStable = useCallback((md: string) => {
    setBody(md);
    if (!userEditedRef.current) {
      setSavedBody((saved) => (isDocMarkdownDirty(md, saved) ? saved : md));
    }
  }, []);

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

  const handleMergeSave = useCallback(async () => {
    if (!mergeReview || saving || readOnly || !doc) return;
    setSaving(true);
    setSaveError(null);
    try {
      await saveDoc(path, body);
      onMergeReviewChange?.({ userModified: true });
      onSaved?.(path);
      const gen = ++loadGenRef.current;
      await loadDoc(path, gen);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }, [
    body,
    doc,
    loadDoc,
    mergeReview,
    onMergeReviewChange,
    onSaved,
    path,
    readOnly,
    saving,
  ]);

  const ensureMergeActionConfirmed = useCallback(
    async (action: "regenerate" | "reject") => {
      if (!mergeReview) return false;
      const message =
        action === "regenerate"
          ? "你已修改当前合并结果。重新生成会覆盖这些修改，确定继续吗？"
          : "你已修改当前合并结果。删除此文会丢失这些修改，确定继续吗？";
      if (mergeReview.userModified) return window.confirm(message);
      try {
        const session = await getMergeSession(mergeReview.mergeId);
        if (session.user_modified) return window.confirm(message);
      } catch {
        return window.confirm("无法确认当前是否已修改，仍要继续吗？");
      }
      return true;
    },
    [mergeReview],
  );

  const runMergeAction = useCallback(
    async (action: "reject" | "regenerate" | "accept", fn?: () => void | Promise<void>) => {
      if (!fn || mergeBusyAction) return;
      setMergeBusyAction(action);
      try {
        await Promise.resolve(fn());
      } finally {
        setMergeBusyAction(null);
      }
    },
    [mergeBusyAction],
  );

  useEffect(() => {
    if (!highlightText || loading || !doc || !bodyRef.current) return;

    const container = bodyRef.current.querySelector(".doc-markdown");
    if (!container) return;

    const prev = container.querySelector(".highlight");
    prev?.classList.remove("highlight");

    const needle = highlightText.trim().slice(0, 120);
    if (!needle) return;

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node: Text | null = walker.nextNode() as Text | null;
    while (node) {
      const idx = node.textContent?.indexOf(needle) ?? -1;
      if (idx >= 0) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + needle.length);
        const mark = document.createElement("mark");
        mark.className = "highlight";
        try {
          range.surroundContents(mark);
          mark.scrollIntoView({ behavior: "smooth", block: "center" });
        } catch {
          mark.textContent = needle;
          node.parentNode?.insertBefore(mark, node);
          mark.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        break;
      }
      node = walker.nextNode() as Text | null;
    }
  }, [highlightText, loading, doc, path, body, editMode]);

  const title =
    (doc?.meta?.title as string | undefined) ||
    path.split("/").pop() ||
    path;

  const conversationId =
    typeof doc?.meta?.conversation_id === "string"
      ? doc.meta.conversation_id
      : null;

  const overflowItems = [
    ...(dirty && !readOnly
      ? [
          {
            id: "view-diff",
            label: "查看变更",
            icon: "diff" as const,
            onClick: () => setUnsavedPrompt("view"),
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
            onClick: () => setMergeEditing((v) => !v),
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
    <div
      className={`doc-viewer${mode === "panel" ? " doc-viewer-panel" : ""}${
        mode === "float" ? " doc-viewer-float" : ""
      }${docFocus ? " doc-viewer-focus" : ""}`}
    >
      <header className="doc-viewer-header">
        {mode === "panel" || mode === "float" ? (
          <button
            type="button"
            className="doc-close-btn"
            onClick={handleClose}
            title="关闭"
          >
            ×
          </button>
        ) : (
          <button type="button" className="doc-back-btn" onClick={handleClose}>
            ← 对话
          </button>
        )}
        <div className="doc-viewer-title">
          {mode === "panel" && <span className="doc-path">{path}</span>}
          <h2>
            {title}
            {dirty && (
              <span
                className="doc-dirty-dot"
                title="有未保存的修改"
                aria-label="有未保存的修改"
              />
            )}
          </h2>
        </div>
        <div className="doc-viewer-toolbar">
          <div className="doc-mode-toggle" role="group" aria-label="编辑模式">
            <DocIconBtn
              className="doc-mode-toggle-btn"
              label="预览模式"
              active={editMode === "preview"}
              onClick={() => handleEditModeChange("preview")}
              disabled={loading || mergeEditing}
            >
              <PreviewIcon />
            </DocIconBtn>
            <DocIconBtn
              className="doc-mode-toggle-btn"
              label="Markdown 源码"
              active={editMode === "markdown"}
              onClick={() => handleEditModeChange("markdown")}
              disabled={loading || mergeEditing}
            >
              <MarkdownIcon />
            </DocIconBtn>
          </div>
          {!readOnly && (
            <>
              {dirty && (
                <DocIconBtn
                  label="放弃未保存的修改"
                  onClick={() => void handleDiscard()}
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
                  void (mergeReview && mergeEditing ? handleMergeSave() : handleSave())
                }
              >
                <SaveIcon />
              </DocIconBtn>
              {dirty && (
                <DocIconBtn
                  label="查看变更"
                  onClick={() => setUnsavedPrompt("view")}
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
                  onToggle={() => setOutlineOpen((v) => !v)}
                  onClose={() => setOutlineOpen(false)}
                  items={outlineItems}
                  activeIndex={outlineActiveIndex}
                  onJump={handleOutlineJump}
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
                onToggle={() => setOutlineOpen((v) => !v)}
                onClose={() => setOutlineOpen(false)}
                items={outlineItems}
                activeIndex={outlineActiveIndex}
                onJump={handleOutlineJump}
                disabled={loading}
              />
              <DocOverflowMenu items={overflowItems} disabled={loading} />
            </>
          )}
        </div>
      </header>
      <div className="doc-viewer-body" ref={bodyRef}>
        {loading && <div className="doc-muted">加载中…</div>}
        {error && <div className="doc-error">错误：{error}</div>}
        {saveError && <div className="doc-save-error">保存失败：{saveError}</div>}
        {readOnly && doc && (
          <div className="doc-muted doc-readonly-hint">此文档为只读，无法编辑。</div>
        )}
        {doc && (
          <>
            {doc.meta &&
              Object.keys(doc.meta).some((k) => k !== "conversation_id") && (
              <div className="doc-meta-bar">
                <DocMetaPopover meta={doc.meta} />
              </div>
            )}
            {mergeReview && mergeEditing ? (
              <textarea
                ref={mergeSourceRef}
                className="doc-markdown-source"
                value={body}
                onChange={(e) => handleBodyChange(e.target.value)}
                readOnly={readOnly}
              />
            ) : editMode === "preview" ? (
              <DocLivePreview
                key={`${loadedPath}#${refreshKey}#${previewRemountKey}`}
                initialBody={body}
                onChange={(b) => handleBodyChange(b)}
                onStable={handlePreviewStable}
                onUserEdit={handlePreviewUserEdit}
                readOnly={readOnly}
              />
            ) : (
              <DocMarkdownSource
                ref={markdownSourceRef}
                body={body}
                onChange={handleBodyChange}
                readOnly={readOnly}
                selection={selection}
                onSelectionChange={setSelection}
              />
            )}
          </>
        )}
      </div>
      {mergeReview && (
        <footer className="doc-merge-review-bar">
          <span>正在审阅合并结果（源自 {mergeReview.sourcePaths.length} 篇）</span>
          <div className="doc-merge-review-actions">
            <button
              type="button"
              onClick={() =>
                void (async () => {
                  if (!(await ensureMergeActionConfirmed("reject"))) return;
                  await runMergeAction("reject", onMergeReject);
                })()
              }
              disabled={mergeBusyAction !== null}
            >
              删除此文
            </button>
            <button
              type="button"
              onClick={() =>
                void (async () => {
                  if (!(await ensureMergeActionConfirmed("regenerate"))) return;
                  await runMergeAction("regenerate", onMergeRegenerate);
                })()
              }
              disabled={mergeBusyAction !== null}
            >
              重新生成
            </button>
            <button
              type="button"
              className="doc-merge-review-accept"
              onClick={() => void runMergeAction("accept", onMergeAccept)}
              disabled={mergeBusyAction !== null}
            >
              采用
            </button>
          </div>
        </footer>
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
