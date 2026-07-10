import { useState } from "react";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";
import { DocViewer } from "./components/DocViewer";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import type { SourceRef } from "./api";

export default function App() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [view, setView] = useState<"chat" | "doc">("chat");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
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

  function openFile(path: string, excerpt?: string) {
    setSelectedPath(path);
    setHighlightText(excerpt);
    setView("doc");
  }

  function openChat() {
    setView("chat");
    setHighlightText(undefined);
  }

  function newChat() {
    setActiveConversationId(null);
    setView("chat");
  }

  function selectConversation(id: string) {
    setActiveConversationId(id);
    setView("chat");
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "kb") {
      openFile(src.path, src.excerpt);
    } else if (src.type === "web") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    } else if (src.type === "search") {
      setSnippetSource(src);
    }
  }

  const chatProps = {
    conversationId: activeConversationId,
    onConversationCreated: setActiveConversationId,
    onSidebarRefresh: refreshSidebar,
    onOpenSource: handleOpenSource,
  };

  return (
    <div className="app-shell">
      <Sidebar
        refreshKey={sidebarRefreshKey}
        selectedPath={selectedPath}
        activeView={view}
        activeConversationId={activeConversationId}
        onSelectFile={(path) => openFile(path)}
        onOpenChat={openChat}
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
        {view === "chat" ? (
          <Chat {...chatProps} />
        ) : selectedPath ? (
          <DocViewer
            path={selectedPath}
            highlightText={highlightText}
            onBack={openChat}
          />
        ) : (
          <Chat {...chatProps} />
        )}
      </main>
      <SearchSnippetModal
        source={snippetSource}
        onClose={() => setSnippetSource(null)}
      />
    </div>
  );
}
