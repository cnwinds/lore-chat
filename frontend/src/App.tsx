import { useEffect, useState } from "react";
import {
  createConversation,
  listConversations,
  type SourceRef,
} from "./api";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
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
  const [docFocus, setDocFocus] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

  function openDocPreview(path: string, excerpt?: string) {
    setPreviewPath(path);
    setHighlightText(excerpt);
  }

  function closeDocPreview() {
    setPreviewPath(null);
    setHighlightText(undefined);
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
      else closeDocPreview();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewPath, docFocus, snippetSource]);

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

  return (
    <div
      className={`app-shell${docFocus && previewPath ? " app-shell--doc-focus" : ""}`}
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
      />
      <main className="main-panel">
        <Chat {...chatProps} />
      </main>
      {previewPath && (
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
            onToggleWidth={toggleDocWidth}
            onToggleFocus={toggleDocFocus}
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
