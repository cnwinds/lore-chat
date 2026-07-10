import { useState } from "react";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
import { DocViewer } from "./components/DocViewer";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import type { SourceRef } from "./api";

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

  function openDocPreview(path: string, excerpt?: string) {
    setPreviewPath(path);
    setHighlightText(excerpt);
  }

  function closeDocPreview() {
    setPreviewPath(null);
    setHighlightText(undefined);
  }

  function newChat() {
    setActiveConversationId(null);
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

  const chatProps = {
    conversationId: activeConversationId,
    previewPath,
    onConversationCreated: handleConversationCreated,
    onSidebarRefresh: refreshSidebar,
    onKbChanged: refreshKb,
    onOpenSource: handleOpenSource,
    onOpenDoc: openDocPreview,
  };

  return (
    <div className="app-shell">
      <Sidebar
        refreshKey={sidebarRefreshKey}
        selectedPath={previewPath}
        activeConversationId={activeConversationId}
        onSelectFile={(path) => openDocPreview(path)}
        onNewChat={newChat}
        onSelectConversation={selectConversation}
        onDeleteConversation={(id) => {
          if (activeConversationId === id) {
            setActiveConversationId(null);
          }
          refreshSidebar();
        }}
      />
      <main className="main-panel">
        <Chat {...chatProps} />
      </main>
      {previewPath && (
        <aside className="doc-panel">
          <DocViewer
            path={previewPath}
            refreshKey={docRefreshKey}
            highlightText={highlightText}
            mode="panel"
            onClose={closeDocPreview}
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
