import { useEffect, useRef, useState } from "react";
import {
  acceptMerge,
  createConversation,
  getActiveMerge,
  listConversations,
  regenerateMerge,
  rejectMerge,
  type SourceRef,
} from "./api";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
import { DocViewer } from "./components/DocViewer";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { MergeSourceQuestion } from "./components/MergeSourceQuestion";
import { isSystemLayerPath } from "./utils/fileTree";

type DocWidth = "narrow" | "wide";

export default function App() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [docRefreshKey, setDocRefreshKey] = useState(0);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [highlightText, setHighlightText] = useState<string | undefined>();
  const [snippetSource, setSnippetSource] = useState<Extract<
    SourceRef,
    { type: "search" }
  > | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
  /** 首问乐观标题；服务端仍为「新对话」时优先展示，刷新后若已更新则自然让位 */
  const [titleOverrides, setTitleOverrides] = useState<Record<string, string>>(
    {},
  );
  const [docWidth, setDocWidth] = useState<DocWidth>("narrow");
  const [docPinned, setDocPinned] = useState(false);
  const [docFocus, setDocFocus] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [docs, setDocs] = useState<string[]>([]);
  const [mergeReview, setMergeReview] = useState<{
    mergeId: string;
    newPath: string;
    sourcePaths: string[];
    userModified: boolean;
  } | null>(null);
  const [mergeSourceQuestion, setMergeSourceQuestion] = useState<{
    mergeId: string;
    newPath: string;
    sourcePaths: string[];
    questionId?: string;
  } | null>(null);
  const lastSelectedPathRef = useRef<string | null>(null);
  const docCloseRef = useRef<(() => void) | null>(null);

  function bindDocClose(handler: (() => void) | null) {
    docCloseRef.current = handler;
  }

  function requestCloseDocPreview() {
    if (docCloseRef.current) docCloseRef.current();
    else closeDocPreview();
  }

  function refreshSidebar() {
    setSidebarRefreshKey((k) => k + 1);
  }

  function clearSelection() {
    setSelectedPaths(new Set());
    lastSelectedPathRef.current = null;
  }

  function toggleSelectionMode() {
    setSelectionMode((prev) => {
      if (prev) clearSelection();
      return !prev;
    });
  }

  /** 知识库内容变更：刷新目录树，并在需要时重载当前预览文档 */
  function refreshKb(changedPath?: string) {
    refreshSidebar();
    if (
      previewPath &&
      (!changedPath ||
        changedPath === previewPath ||
        previewPath.startsWith(`${changedPath}/`))
    ) {
      setDocRefreshKey((k) => k + 1);
    }
  }

  function handleConversationCreated(id: string) {
    setActiveConversationId(id);
    refreshSidebar();
  }

  function handleFirstQuestionTitle(id: string, title: string) {
    setTitleOverrides((prev) => ({ ...prev, [id]: title }));
  }

  function openDocPreview(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    const wantPin = options?.pin;

    if (path === previewPath && !docPinned && wantPin !== true) {
      requestCloseDocPreview();
      return;
    }

    setPreviewPath(path);
    setHighlightText(excerpt);

    if (wantPin === true) {
      setDocPinned(true);
    } else if (wantPin === false) {
      setDocPinned(false);
      setDocFocus(false);
    } else if (!docPinned) {
      setDocPinned(false);
      setDocFocus(false);
    }
  }

  function pinDocPreview() {
    if (!previewPath) return;
    setDocPinned(true);
  }

  function unpinDocPreview() {
    if (!previewPath) return;
    setDocPinned(false);
    setDocFocus(false);
    setSidebarCollapsed(false);
  }

  function closeDocPreview() {
    setPreviewPath(null);
    setHighlightText(undefined);
    setDocPinned(false);
    setDocFocus(false);
    setSidebarCollapsed(false);
    setMergeReview(null);
    // docWidth intentionally retained
  }

  function enterDocFocus() {
    setDocFocus(true);
    setSidebarCollapsed(true);
  }

  function exitDocFocus() {
    setDocFocus(false);
    setSidebarCollapsed(false);
  }

  function toggleDocWidth() {
    setDocWidth((w) => (w === "narrow" ? "wide" : "narrow"));
  }

  function toggleDocFocus() {
    if (docFocus) exitDocFocus();
    else enterDocFocus();
  }

  async function newChat() {
    try {
      const { conversations } = await listConversations();
      const empty =
        conversations.find(
          (c) => c.id === activeConversationId && c.message_count === 0,
        ) ?? conversations.find((c) => c.message_count === 0);
      if (empty) {
        setActiveConversationId(empty.id);
        return;
      }
      const { id } = await createConversation();
      setActiveConversationId(id);
      refreshSidebar();
    } catch {
      setActiveConversationId(null);
    }
  }

  function selectConversation(id: string) {
    setActiveConversationId(id);
    requestCloseDocPreview();
  }

  function openConversationFromDoc(id: string) {
    setActiveConversationId(id);
    requestCloseDocPreview();
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "kb") {
      openDocPreview(src.path, src.excerpt);
    } else if (src.type === "web") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    } else if (src.type === "search") {
      setSnippetSource(src);
    }
  }

  function handleToggleSelect(path: string, shiftKey?: boolean) {
    if (isSystemLayerPath(path)) return;
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      const sameFolder = (a: string, b: string) =>
        a.slice(0, Math.max(0, a.lastIndexOf("/"))) ===
        b.slice(0, Math.max(0, b.lastIndexOf("/")));
      const lastPath = lastSelectedPathRef.current;
      if (shiftKey && lastPath && sameFolder(lastPath, path)) {
        const folder = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
        const folderDocs = docs
          .filter((p) => {
            if (isSystemLayerPath(p)) return false;
            const currentFolder = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
            return currentFolder === folder;
          })
          .sort((a, b) => a.localeCompare(b, "zh-CN"));
        const start = folderDocs.indexOf(lastPath);
        const end = folderDocs.indexOf(path);
        if (start >= 0 && end >= 0) {
          const [from, to] = start < end ? [start, end] : [end, start];
          folderDocs.slice(from, to + 1).forEach((p) => next.add(p));
          lastSelectedPathRef.current = path;
          return next;
        }
      }
      if (next.has(path)) next.delete(path);
      else next.add(path);
      lastSelectedPathRef.current = path;
      return next;
    });
  }

  function handleSelectFolderAll(paths: string[]) {
    if (paths.length === 0) return;
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      paths.forEach((path) => {
        if (!isSystemLayerPath(path)) next.add(path);
      });
      return next;
    });
  }

  function handleMergeComplete(result: {
    merge_id: string | null;
    rel_path: string | null;
    source_paths: string[];
    user_modified: boolean;
  }) {
    if (!result.merge_id || !result.rel_path) return;
    openDocPreview(result.rel_path, undefined, { pin: true });
    setMergeReview({
      mergeId: result.merge_id,
      newPath: result.rel_path,
      sourcePaths: result.source_paths,
      userModified: result.user_modified,
    });
    setMergeSourceQuestion(null);
    refreshKb();
    setSelectionMode(false);
    clearSelection();
  }

  useEffect(() => {
    if (!previewPath) {
      setMergeReview(null);
      return;
    }
    let cancelled = false;
    void getActiveMerge(previewPath)
      .then((session) => {
        if (cancelled) return;
        if (!session || session.status !== "pending_review") {
          setMergeReview((prev) => (prev?.newPath === previewPath ? null : prev));
          return;
        }
        setMergeReview({
          mergeId: session.id,
          newPath: session.new_path,
          sourcePaths: session.source_paths,
          userModified: session.user_modified,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setMergeReview((prev) => (prev?.newPath === previewPath ? null : prev));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [previewPath]);

  async function handleMergeAccept() {
    if (!mergeReview) return;
    const current = mergeReview;
    try {
      const result = await acceptMerge(current.mergeId);
      setMergeReview(null);
      refreshKb(current.newPath);
      if (result.question_id) {
        setMergeSourceQuestion({
          mergeId: current.mergeId,
          newPath: current.newPath,
          sourcePaths: current.sourcePaths,
          questionId: result.question_id,
        });
      } else {
        setMergeSourceQuestion(null);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "采用失败");
    }
  }

  async function handleMergeRegenerate() {
    if (!mergeReview) return;
    try {
      const result = await regenerateMerge(mergeReview.mergeId);
      setMergeReview((prev) =>
        prev
          ? {
              ...prev,
              sourcePaths: result.source_paths.length > 0 ? result.source_paths : prev.sourcePaths,
              userModified: false,
            }
          : prev,
      );
      setDocRefreshKey((k) => k + 1);
      refreshKb(mergeReview.newPath);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "重新生成失败");
    }
  }

  async function handleMergeReject() {
    if (!mergeReview) return;
    try {
      await rejectMerge(mergeReview.mergeId);
      closeDocPreview();
      setMergeReview(null);
      setMergeSourceQuestion(null);
      refreshKb();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "删除失败");
    }
  }

  useEffect(() => {
    if (!previewPath && !snippetSource && !selectionMode) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (snippetSource !== null) {
        setSnippetSource(null);
        return;
      }
      if (selectionMode) {
        setSelectionMode(false);
        clearSelection();
        return;
      }
      if (!previewPath) return;
      if (docFocus) exitDocFocus();
      else requestCloseDocPreview();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewPath, docFocus, docPinned, snippetSource, selectionMode]);

  const chatProps = {
    conversationId: activeConversationId,
    previewPath,
    onConversationCreated: handleConversationCreated,
    onFirstQuestionTitle: handleFirstQuestionTitle,
    onSidebarRefresh: refreshSidebar,
    onKbChanged: refreshKb,
    onOpenSource: handleOpenSource,
    onOpenDoc: openDocPreview,
  };

  const floatFocus = docFocus && previewPath && !docPinned;
  const panelFocus = docFocus && previewPath && docPinned;
  const activeMergeReview =
    mergeReview && previewPath === mergeReview.newPath
      ? {
          mergeId: mergeReview.mergeId,
          sourcePaths: mergeReview.sourcePaths,
          userModified: mergeReview.userModified,
        }
      : null;

  return (
    <div
      className={`app-shell${panelFocus ? " app-shell--doc-focus" : ""}${
        floatFocus ? " app-shell--doc-focus-float" : ""
      }`}
      data-has-merge-review={mergeReview ? "1" : "0"}
    >
      <Sidebar
        refreshKey={sidebarRefreshKey}
        selectedPath={previewPath}
        activeConversationId={activeConversationId}
        titleOverrides={titleOverrides}
        collapsed={docFocus && previewPath ? sidebarCollapsed : false}
        onToggleCollapsed={
          docFocus && previewPath
            ? () => setSidebarCollapsed((c) => !c)
            : undefined
        }
        onSelectFile={(path) => openDocPreview(path)}
        onNewChat={() => {
          void newChat();
        }}
        onSelectConversation={selectConversation}
        onDeleteConversation={(id) => {
          if (activeConversationId === id) {
            setActiveConversationId(null);
          }
          setTitleOverrides((prev) => {
            if (!(id in prev)) return prev;
            const next = { ...prev };
            delete next[id];
            return next;
          });
          refreshSidebar();
        }}
        selectionMode={selectionMode}
        selectedPaths={selectedPaths}
        onToggleSelectionMode={toggleSelectionMode}
        onToggleSelect={handleToggleSelect}
        onSelectFolderAll={handleSelectFolderAll}
        onMergeComplete={handleMergeComplete}
        onDocsLoaded={setDocs}
      />
      <main
        className={`main-panel${
          previewPath && !docPinned && docWidth === "wide" && !docFocus
            ? " main-panel--float-wide"
            : ""
        }`}
      >
        <Chat {...chatProps} />
        {previewPath && !docPinned && (
          <>
            {!docFocus && (
              <div
                className="doc-float-backdrop"
                aria-hidden
                onClick={requestCloseDocPreview}
              />
            )}
            <div
              className="doc-float-panel"
              onClick={(e) => e.stopPropagation()}
              onMouseDown={(e) => e.stopPropagation()}
            >
              <DocViewer
                path={previewPath}
                refreshKey={docRefreshKey}
                highlightText={highlightText}
                mode="float"
                docWidth={docWidth}
                docFocus={docFocus}
                onClose={closeDocPreview}
                onBindClose={bindDocClose}
                onSaved={(p) => refreshKb(p)}
                onNavigationBlocked={(stayPath) => setPreviewPath(stayPath)}
                onPin={pinDocPreview}
                onToggleWidth={toggleDocWidth}
                onToggleFocus={toggleDocFocus}
                onOpenConversation={openConversationFromDoc}
                mergeReview={activeMergeReview}
                onMergeReviewChange={(patch) =>
                  setMergeReview((prev) => (prev ? { ...prev, ...patch } : prev))
                }
                onMergeAccept={handleMergeAccept}
                onMergeRegenerate={handleMergeRegenerate}
                onMergeReject={handleMergeReject}
              />
            </div>
          </>
        )}
      </main>
      {previewPath && docPinned && (
        <aside
          className={
            docFocus
              ? "doc-panel"
              : `doc-panel doc-panel--${docWidth}`
          }
        >
          <DocViewer
            path={previewPath}
            refreshKey={docRefreshKey}
            highlightText={highlightText}
            mode="panel"
            docWidth={docWidth}
            docFocus={docFocus}
            onClose={closeDocPreview}
            onBindClose={bindDocClose}
            onSaved={(p) => refreshKb(p)}
            onNavigationBlocked={(stayPath) => setPreviewPath(stayPath)}
            onUnpin={unpinDocPreview}
            onToggleWidth={toggleDocWidth}
            onToggleFocus={toggleDocFocus}
            onOpenConversation={openConversationFromDoc}
            mergeReview={activeMergeReview}
            onMergeReviewChange={(patch) =>
              setMergeReview((prev) => (prev ? { ...prev, ...patch } : prev))
            }
            onMergeAccept={handleMergeAccept}
            onMergeRegenerate={handleMergeRegenerate}
            onMergeReject={handleMergeReject}
          />
        </aside>
      )}
      {mergeSourceQuestion && (
        <MergeSourceQuestion
          mergeId={mergeSourceQuestion.mergeId}
          newPath={mergeSourceQuestion.newPath}
          sourcePaths={mergeSourceQuestion.sourcePaths}
          onDone={() => {
            if (previewPath === mergeSourceQuestion.newPath) {
              setDocRefreshKey((k) => k + 1);
            }
            setMergeSourceQuestion(null);
            refreshKb();
          }}
        />
      )}
      <SearchSnippetModal
        source={snippetSource}
        onClose={() => setSnippetSource(null)}
      />
    </div>
  );
}
