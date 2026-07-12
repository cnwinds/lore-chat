import { useEffect, useRef, useState } from "react";
import {
  createConversation,
  listConversations,
  type SourceRef,
} from "./api";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
import { useComposerDocState } from "./hooks/useComposerDocState";
import { DocViewer } from "./components/DocViewer";
import { SearchSnippetModal } from "./components/SearchSnippetModal";

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
  const docCloseRef = useRef<(() => void) | null>(null);
  const composer = useComposerDocState();

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

    const title = path.split("/").pop() ?? path;
    if (!composer.paths.includes(path)) {
      composer.addToTray(path, title);
    }
    composer.setPrimary(path);

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

  function handleSelectFile(
    path: string,
    mods?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
  ) {
    const title = path.split("/").pop() ?? path;
    if (mods?.ctrlKey || mods?.metaKey || mods?.shiftKey) {
      composer.addToTray(path, title);
    } else {
      composer.replaceTray(path, title);
      openDocPreview(path, undefined, { pin: true });
    }
  }

  function handleTraySetPrimary(path: string) {
    composer.setPrimary(path);
    openDocPreview(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    const nextPrimary =
      composer.primaryPath !== path
        ? composer.primaryPath
        : (composer.items.find((i) => i.path !== path)?.path ?? null);
    composer.removeFromTray(path);
    if (previewPath === path && nextPrimary === null) {
      closeDocPreview();
    }
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

  useEffect(() => {
    if (!previewPath && !snippetSource) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (snippetSource !== null) {
        setSnippetSource(null);
        return;
      }
      if (!previewPath) return;
      if (docFocus) exitDocFocus();
      else requestCloseDocPreview();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewPath, docFocus, docPinned, snippetSource]);

  const chatProps = {
    conversationId: activeConversationId,
    previewPath,
    onConversationCreated: handleConversationCreated,
    onFirstQuestionTitle: handleFirstQuestionTitle,
    onSidebarRefresh: refreshSidebar,
    onKbChanged: refreshKb,
    onOpenSource: handleOpenSource,
    onOpenDoc: openDocPreview,
    docTrayItems: composer.items,
    primaryDocPath: composer.primaryPath,
    docPaths: composer.paths,
    onTraySetPrimary: handleTraySetPrimary,
    onTrayRemove: handleTrayRemove,
  };

  const floatFocus = docFocus && previewPath && !docPinned;
  const panelFocus = docFocus && previewPath && docPinned;

  return (
    <div
      className={`app-shell${panelFocus ? " app-shell--doc-focus" : ""}${
        floatFocus ? " app-shell--doc-focus-float" : ""
      }`}
    >
      <Sidebar
        refreshKey={sidebarRefreshKey}
        selectedPath={composer.primaryPath ?? previewPath}
        activeConversationId={activeConversationId}
        titleOverrides={titleOverrides}
        collapsed={docFocus && previewPath ? sidebarCollapsed : false}
        onToggleCollapsed={
          docFocus && previewPath
            ? () => setSidebarCollapsed((c) => !c)
            : undefined
        }
        onSelectFile={handleSelectFile}
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
          />
        </aside>
      )}
      <SearchSnippetModal
        source={snippetSource}
        onClose={() => setSnippetSource(null)}
      />
    </div>
  );
}
