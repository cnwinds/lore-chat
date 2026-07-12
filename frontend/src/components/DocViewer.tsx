import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDoc, saveDoc, type DocContent } from "../api";
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
import { useDocOutlineActive } from "../hooks/useDocOutlineActive";
import { isDocMarkdownDirty } from "../utils/docMarkdown";
import {
  jumpToOutlineInPreview,
  jumpToOutlineInSource,
  parseDocOutline,
  type OutlineItem,
} from "../utils/docOutline";

type DocWidth = "narrow" | "wide";
type DocMode = "panel" | "float" | "page";
type EditMode = "preview" | "markdown";

const EDIT_MODE_KEY = "docEditMode";

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
};

function getStoredEditMode(): EditMode {
  try {
    return sessionStorage.getItem(EDIT_MODE_KEY) === "markdown"
      ? "markdown"
      : "preview";
  } catch {
    return "preview";
  }
}

function setStoredEditMode(mode: EditMode) {
  try {
    sessionStorage.setItem(EDIT_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

function isReadOnlyPath(path: string): boolean {
  const norm = path.replace(/\\/g, "/");
  return (
    norm.startsWith(".kb/") ||
    norm.startsWith(".git/") ||
    norm === ".kb" ||
    norm === ".git"
  );
}

type UnsavedPrompt = "view" | "close" | "navigate" | "reload";

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
}: Props) {
  const [doc, setDoc] = useState<DocContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editMode, setEditMode] = useState<EditMode>(getStoredEditMode);
  const [body, setBody] = useState("");
  const [savedBody, setSavedBody] = useState("");
  const [selection, setSelection] = useState<DocSelection>({ start: 0, end: 0 });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loadedPath, setLoadedPath] = useState(path);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [unsavedPrompt, setUnsavedPrompt] = useState<UnsavedPrompt | null>(null);
  const [previewRemountKey, setPreviewRemountKey] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  const markdownSourceRef = useRef<HTMLTextAreaElement>(null);
  const loadGenRef = useRef(0);
  const lastRefreshKeyRef = useRef(refreshKey);
  const userEditedRef = useRef(false);
  const pendingNavRef = useRef<{ targetPath: string; gen: number } | null>(null);
  const unsavedPromptRef = useRef<UnsavedPrompt | null>(null);
  unsavedPromptRef.current = unsavedPrompt;

  const readOnly = isReadOnlyPath(path);
  const dirty = isDocMarkdownDirty(body, savedBody);
  const outlineItems = useMemo(() => parseDocOutline(body), [body]);
  const outlineInSource = editMode === "markdown";
  const outlineActiveIndex = useDocOutlineActive({
    items: outlineItems,
    inSource: outlineInSource,
    scrollRootRef: bodyRef,
    sourceRef: markdownSourceRef,
    enabled: Boolean(doc) && !loading,
  });

  const loadDoc = useCallback(async (targetPath: string, gen: number) => {
    setLoading(true);
    setError(null);
    setSaveError(null);
    try {
      const d = await getDoc(targetPath);
      if (gen !== loadGenRef.current) return;
      setDoc(d);
      setBody(d.body);
      setSavedBody(d.body);
      setSelection({ start: d.body.length, end: d.body.length });
      setLoadedPath(targetPath);
      userEditedRef.current = false;
      setPreviewRemountKey((k) => k + 1);
    } catch (e) {
      if (gen !== loadGenRef.current) return;
      setDoc(null);
      setBody("");
      setSavedBody("");
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (gen === loadGenRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const gen = ++loadGenRef.current;
    const pathChanged = path !== loadedPath;
    const refreshChanged = refreshKey !== lastRefreshKeyRef.current;
    lastRefreshKeyRef.current = refreshKey;

    if (dirty && (pathChanged || refreshChanged)) {
      pendingNavRef.current = { targetPath: path, gen };
      setUnsavedPrompt(pathChanged ? "navigate" : "reload");
      if (pathChanged) onNavigationBlocked?.(loadedPath);
      return;
    }

    void loadDoc(path, gen);
  }, [path, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setOutlineOpen(false);
  }, [path, refreshKey]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "s") return;
      e.preventDefault();
      void handleSaveRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleSaveRef = useRef<() => Promise<void>>(async () => {});

  const handleSave = useCallback(async (): Promise<boolean> => {
    if (!dirty || saving || readOnly || !doc) return !dirty;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveDoc(path, body);
      setDoc(saved);
      setSavedBody(body);
      onSaved?.(path);
      return true;
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [body, dirty, doc, onSaved, path, readOnly, saving]);

  handleSaveRef.current = async () => {
    await handleSave();
  };

  const finishClose = useCallback(() => {
    if (onCloseRequest && !onCloseRequest()) return;
    onClose();
  }, [onClose, onCloseRequest]);

  const applyDiscard = useCallback(() => {
    userEditedRef.current = false;
    setBody(savedBody);
    setSelection({ start: savedBody.length, end: savedBody.length });
    setSaveError(null);
    setPreviewRemountKey((k) => k + 1);
  }, [savedBody]);

  const completePendingNavigation = useCallback(() => {
    const pending = pendingNavRef.current;
    pendingNavRef.current = null;
    setUnsavedPrompt(null);
    if (pending) void loadDoc(pending.targetPath, pending.gen);
  }, [loadDoc]);

  const cancelUnsavedPrompt = useCallback(() => {
    pendingNavRef.current = null;
    setUnsavedPrompt(null);
  }, []);

  const resolveUnsavedPromptAfterAction = useCallback(
    (action: "discard" | "save") => {
      const prompt = unsavedPromptRef.current;
      if (!prompt || prompt === "view") return;

      if (action === "discard") applyDiscard();

      if (prompt === "close") {
        pendingNavRef.current = null;
        setUnsavedPrompt(null);
        finishClose();
        return;
      }

      if (prompt === "navigate" || prompt === "reload") {
        completePendingNavigation();
      }
    },
    [applyDiscard, completePendingNavigation, finishClose],
  );

  const handleConfirmDiscard = useCallback(() => {
    resolveUnsavedPromptAfterAction("discard");
  }, [resolveUnsavedPromptAfterAction]);

  const handleConfirmSave = useCallback(async () => {
    const prompt = unsavedPromptRef.current;
    if (!prompt || prompt === "view") return;

    const ok = await handleSave();
    if (!ok) return;
    resolveUnsavedPromptAfterAction("save");
  }, [handleSave, resolveUnsavedPromptAfterAction]);

  const handleClose = useCallback(() => {
    if (dirty) {
      setUnsavedPrompt("close");
      return;
    }
    finishClose();
  }, [dirty, finishClose]);

  useEffect(() => {
    onBindClose?.(handleClose);
    return () => onBindClose?.(null);
  }, [handleClose, onBindClose]);

  const handleEditModeChange = (mode: EditMode) => {
    setEditMode(mode);
    setStoredEditMode(mode);
  };

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

  const handleDiscard = useCallback(() => {
    if (!dirty || saving) return;
    if (!window.confirm("放弃未保存的修改？此操作不可撤销。")) return;
    applyDiscard();
    setUnsavedPrompt(null);
  }, [applyDiscard, dirty, saving]);

  const handleOutlineJump = useCallback(
    (item: OutlineItem) => {
      if (editMode === "markdown") {
        jumpToOutlineInSource(markdownSourceRef.current, item.line);
      } else {
        jumpToOutlineInPreview(bodyRef.current, item);
      }
    },
    [editMode],
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
  const canSave = !readOnly && dirty && !saving && !loading;

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
              disabled={loading}
            >
              <PreviewIcon />
            </DocIconBtn>
            <DocIconBtn
              className="doc-mode-toggle-btn"
              label="Markdown 源码"
              active={editMode === "markdown"}
              onClick={() => handleEditModeChange("markdown")}
              disabled={loading}
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
                muted={!dirty}
                disabled={!canSave}
                onClick={() => void handleSave()}
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
            {editMode === "preview" ? (
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
