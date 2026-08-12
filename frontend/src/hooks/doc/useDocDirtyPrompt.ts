import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import { saveDoc, type DocContent } from "../../api";
import type { DocSelection } from "../../components/DocLivePreview";
import type { UnsavedPrompt } from "../../types/doc";
import { isDocMarkdownDirty } from "../../utils/docMarkdown";

export type MergeReviewInfo = {
  mergeId: string;
  sourcePaths: string[];
  userModified: boolean;
};

export type UnsavedResolution =
  | { kind: "finishClose" }
  | { kind: "completeNavigation" }
  | { kind: "noop" };

/**
 * 未保存弹窗在「放弃/保存后」应触发的收尾动作。
 * 抽成纯函数便于单测覆盖状态机分支，不依赖 React。
 */
export function nextUnsavedAfterDiscard(prompt: UnsavedPrompt): UnsavedResolution {
  if (prompt === "close") return { kind: "finishClose" };
  if (prompt === "navigate" || prompt === "reload") {
    return { kind: "completeNavigation" };
  }
  return { kind: "noop" };
}

type UseDocDirtyPromptOptions = {
  path: string;
  refreshKey: number;
  readOnly: boolean;
  onClose: () => void;
  /** 向父组件注册带 dirty 检查的关闭函数（用于点击浮层背景等外部关闭） */
  onBindClose?: (close: (() => void) | null) => void;
  onCloseRequest?: () => boolean;
  onSaved?: (path: string) => void;
  onNavigationBlocked?: (stayPath: string) => void;
  mergeReview?: MergeReviewInfo | null;
  mergeEditing: boolean;
  onMergeReviewChange?: (patch: Partial<{ userModified: boolean }>) => void;
  // 来自 useDocLoader 的加载状态
  doc: DocContent | null;
  setDoc: Dispatch<SetStateAction<DocContent | null>>;
  body: string;
  setBody: Dispatch<SetStateAction<string>>;
  savedBody: string;
  setSavedBody: Dispatch<SetStateAction<string>>;
  loadedPath: string;
  loadDoc: (targetPath: string, gen: number) => Promise<void>;
  loadGenRef: MutableRefObject<number>;
  lastRefreshKeyRef: MutableRefObject<number>;
  userEditedRef: MutableRefObject<boolean>;
  bumpPreviewRemount: () => void;
  setSelection: Dispatch<SetStateAction<DocSelection>>;
  // 保存态（DocViewer 持有，合并审阅手动保存也会用到）
  saving: boolean;
  setSaving: Dispatch<SetStateAction<boolean>>;
  setSaveError: Dispatch<SetStateAction<string | null>>;
};

/** Doc 未保存状态机：dirty 判定、未保存弹窗、保存/放弃/关闭/导航守卫。 */
export function useDocDirtyPrompt({
  path,
  refreshKey,
  readOnly,
  onClose,
  onBindClose,
  onCloseRequest,
  onSaved,
  onNavigationBlocked,
  mergeReview = null,
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
}: UseDocDirtyPromptOptions) {
  const [unsavedPrompt, setUnsavedPrompt] = useState<UnsavedPrompt | null>(null);
  const pendingNavRef = useRef<{ targetPath: string; gen: number } | null>(null);
  const unsavedPromptRef = useRef<UnsavedPrompt | null>(null);
  unsavedPromptRef.current = unsavedPrompt;

  const dirty = isDocMarkdownDirty(body, savedBody);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, refreshKey]);

  const handleSaveRef = useRef<() => Promise<void>>(async () => {});

  /** 落盘正文并更新本地 saved 状态；不触发 remount。 */
  const writeBodyToDisk = useCallback(async (): Promise<boolean> => {
    if (saving || readOnly || !doc) return false;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveDoc(path, body);
      setDoc(saved);
      setSavedBody(body);
      return true;
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }, [
    body,
    doc,
    path,
    readOnly,
    saving,
    setDoc,
    setSaveError,
    setSavedBody,
    setSaving,
  ]);

  const handleSave = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    if (!(await writeBodyToDisk())) return false;
    onSaved?.(path);
    return true;
  }, [dirty, onSaved, path, writeBodyToDisk]);

  const handleMergeSave = useCallback(async (): Promise<boolean> => {
    if (!mergeReview) return false;
    if (!dirty) return true;
    if (!(await writeBodyToDisk())) return false;
    onMergeReviewChange?.({ userModified: true });
    onSaved?.(path);
    return true;
  }, [dirty, mergeReview, onMergeReviewChange, onSaved, path, writeBodyToDisk]);

  handleSaveRef.current = async () => {
    if (mergeReview && mergeEditing) await handleMergeSave();
    else await handleSave();
  };

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "s") return;
      e.preventDefault();
      void handleSaveRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const finishClose = useCallback(() => {
    if (onCloseRequest && !onCloseRequest()) return;
    onClose();
  }, [onClose, onCloseRequest]);

  const applyDiscard = useCallback(() => {
    userEditedRef.current = false;
    setBody(savedBody);
    setSelection({ start: savedBody.length, end: savedBody.length });
    setSaveError(null);
    bumpPreviewRemount();
  }, [bumpPreviewRemount, savedBody, setBody, setSaveError, setSelection, userEditedRef]);

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

      const resolution = nextUnsavedAfterDiscard(prompt);
      if (resolution.kind === "finishClose") {
        pendingNavRef.current = null;
        setUnsavedPrompt(null);
        finishClose();
        return;
      }
      if (resolution.kind === "completeNavigation") {
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

    const ok =
      mergeReview && mergeEditing
        ? await handleMergeSave()
        : await handleSave();

    if (!ok) return;
    resolveUnsavedPromptAfterAction("save");
  }, [
    handleMergeSave,
    handleSave,
    mergeEditing,
    mergeReview,
    resolveUnsavedPromptAfterAction,
  ]);

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

  const handleDiscard = useCallback(() => {
    if (!dirty || saving) return;
    if (!window.confirm("放弃未保存的修改？此操作不可撤销。")) return;
    applyDiscard();
    setUnsavedPrompt(null);
  }, [applyDiscard, dirty, saving]);

  return {
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
  };
}
