import { useEffect, useRef, useState } from "react";
import { getAuthStatus, type SourceRef } from "./api";
import { LoginPage } from "./components/auth/LoginPage";
import { SetupPage } from "./components/auth/SetupPage";
import { Chat } from "./components/Chat";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { AppShell } from "./components/app/AppShell";
import { DocFloatLayer } from "./components/app/DocFloatLayer";
import { DocPinnedPanel } from "./components/app/DocPinnedPanel";
import { DocPreviewProvider } from "./contexts/DocPreviewContext";
import { buildDocViewerHandlers } from "./hooks/app/buildDocViewerHandlers";
import { useAppEscapeKey } from "./hooks/app/useAppEscapeKey";
import { useConversationShell } from "./hooks/app/useConversationShell";
import { useDocPreviewLayout } from "./hooks/app/useDocPreviewLayout";
import { useComposerDocState } from "./hooks/useComposerDocState";
import type { JumpTarget } from "./hooks/chat/useConversationJump";

type Gate = "loading" | "setup" | "login" | "app";

export default function App() {
  const [gate, setGate] = useState<Gate>("loading");

  useEffect(() => {
    getAuthStatus()
      .then((s) => {
        if (s.setup_required) setGate("setup");
        else if (!s.authenticated) setGate("login");
        else setGate("app");
      })
      .catch(() => setGate("login"));
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setGate("login");
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, []);

  if (gate === "loading") return null;
  if (gate === "setup") return <SetupPage onDone={() => setGate("app")} />;
  if (gate === "login") return <LoginPage onDone={() => setGate("app")} />;
  return <AppMain />;
}

function AppMain() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [snippetSource, setSnippetSource] = useState<Extract<
    SourceRef,
    { type: "search" }
  > | null>(null);

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const doc = useDocPreviewLayout(refreshSidebar);
  const composer = useComposerDocState();
  const pinAddedTrayRef = useRef<string | null>(null);

  function addDocToComposer(path: string) {
    const title = path.split("/").pop() ?? path;
    if (!composer.paths.includes(path)) {
      composer.addToTray(path, title);
    }
    composer.setPrimary(path);
  }

  function openDocWithComposer(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    addDocToComposer(path);
    doc.openDocPreview(path, excerpt, options);
  }

  function handlePinDoc() {
    const path = doc.floatPath;
    if (!path) return;
    const wasInTray = composer.paths.includes(path);
    if (!wasInTray) {
      pinAddedTrayRef.current = path;
      addDocToComposer(path);
    } else {
      pinAddedTrayRef.current = null;
      composer.setPrimary(path);
    }
    doc.pinDocPreview();
  }

  function handleUnpinDoc() {
    const path = doc.pinnedPath;
    if (path && pinAddedTrayRef.current === path) {
      composer.removeFromTray(path);
      pinAddedTrayRef.current = null;
    }
    doc.unpinDocPreview();
  }

  function handleSelectFile(
    path: string,
    mods?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
  ) {
    const title = path.split("/").pop() ?? path;
    if (mods?.ctrlKey || mods?.metaKey || mods?.shiftKey) {
      composer.addToTray(path, title);
    } else {
      doc.openDocPreview(path, undefined, { pin: false });
    }
  }

  function handleTraySetPrimary(path: string) {
    composer.setPrimary(path);
    openDocWithComposer(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    const nextPrimary =
      composer.primaryPath !== path
        ? composer.primaryPath
        : (composer.items.find((i) => i.path !== path)?.path ?? null);
    composer.removeFromTray(path);
    if (doc.pinnedPath === path && nextPrimary === null) {
      doc.closePinnedPreview();
    }
  }

  const conversation = useConversationShell({
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    composerPrimaryPath: composer.primaryPath,
    onSelectFile: handleSelectFile,
  });

  useAppEscapeKey(doc, snippetSource, () => setSnippetSource(null));

  function handleJumpToConversation(target: JumpTarget) {
    if (conversation.activeConversationId !== target.conversationId) {
      conversation.setActiveConversationId(target.conversationId);
    }
    conversation.requestJump(target);
    doc.closeAllPreviews();
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "kb") openDocWithComposer(src.path, src.excerpt, { pin: true });
    else if (src.type === "web") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    } else if (src.type === "search") {
      setSnippetSource(src);
    }
  }

  const floatDocHandlers = buildDocViewerHandlers(doc, "float", (id) => {
    conversation.setActiveConversationId(id);
    doc.closeAllPreviews();
  });
  const pinnedDocHandlers = buildDocViewerHandlers(doc, "pinned", (id) => {
    conversation.setActiveConversationId(id);
    doc.closeAllPreviews();
  });

  return (
    <DocPreviewProvider value={doc.contextValue}>
      <AppShell
        panelFocus={Boolean(doc.panelFocus)}
        floatFocus={Boolean(doc.floatFocus)}
        hasMergeReview={false}
        mainFloatWide={doc.mainFloatWide}
        sidebarProps={{
          ...conversation.sidebarProps,
          onOpenSettings: () => setSettingsOpen(true),
        }}
        chat={
          <Chat
            conversationId={conversation.activeConversationId}
            onConversationCreated={(id) => {
              conversation.setActiveConversationId(id);
              refreshSidebar();
            }}
            onFirstQuestionTitle={(id, title) =>
              conversation.setTitleOverrides((prev) => ({ ...prev, [id]: title }))
            }
            onSidebarRefresh={refreshSidebar}
            onOpenSource={handleOpenSource}
            onJumpToConversation={handleJumpToConversation}
            pendingJump={conversation.pendingJump}
            onJumpHandled={conversation.clearPendingJump}
            docTrayItems={composer.items}
            primaryDocPath={composer.primaryPath}
            docPaths={composer.paths}
            onTraySetPrimary={handleTraySetPrimary}
            onTrayRemove={handleTrayRemove}
          />
        }
        docFloat={
          doc.showFloat ? (
            <DocFloatLayer
              path={doc.floatPath!}
              refreshKey={doc.floatRefreshKey}
              highlightText={doc.floatHighlight}
              docWidth={doc.floatWidth}
              docFocus={doc.floatFocus}
              showBackdrop={!doc.floatFocus}
              onRequestClose={doc.requestCloseFloatPreview}
              onPin={handlePinDoc}
              {...floatDocHandlers}
            />
          ) : null
        }
        docPinned={
          doc.showPinned ? (
            <DocPinnedPanel
              path={doc.pinnedPath!}
              refreshKey={doc.pinnedRefreshKey}
              highlightText={doc.pinnedHighlight}
              docWidth={doc.pinnedWidth}
              docFocus={doc.pinnedFocus}
              onUnpin={handleUnpinDoc}
              {...pinnedDocHandlers}
            />
          ) : null
        }
        modals={
          <>
            <SearchSnippetModal
              source={snippetSource}
              onClose={() => setSnippetSource(null)}
            />
            <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
          </>
        }
      />
    </DocPreviewProvider>
  );
}
