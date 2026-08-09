import { useEffect, useState } from "react";
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
import { useComposerPreviewBridge } from "./hooks/useComposerPreviewBridge";
import { useSkillTrayAttach } from "./hooks/useSkillTrayAttach";
import type { JumpTarget } from "./hooks/chat/useConversationJump";
import { SkillPickModal } from "./components/SkillPickModal";

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
  const {
    skillPick,
    openSkillPickForFolder,
    handleSkillPickConfirm,
    cancelSkillPick,
  } = useSkillTrayAttach(composer);
  const bridge = useComposerPreviewBridge({
    composer,
    doc,
    refreshSidebar,
    onSearchSource: setSnippetSource,
  });

  function handleSelectFolder(path: string, mods?: { ctrlKey?: boolean; metaKey?: boolean }) {
    if (mods?.ctrlKey || mods?.metaKey) {
      openSkillPickForFolder(path);
    }
  }

  const conversation = useConversationShell({
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    composerPrimaryPath: composer.primaryPath,
    onSelectFile: bridge.handleSelectFile,
    onSelectFolder: handleSelectFolder,
    onAttachSkillsFolder: openSkillPickForFolder,
    onDocsLoaded: bridge.setKbDocs,
    onKbPathChanged: bridge.handleKbPathChanged,
    onKbPathsDeleted: bridge.handleKbPathsDeleted,
  });

  useAppEscapeKey(doc, snippetSource, () => setSnippetSource(null));

  function handleJumpToConversation(target: JumpTarget) {
    if (conversation.activeConversationId !== target.conversationId) {
      conversation.setActiveConversationId(target.conversationId);
    }
    conversation.requestJump(target);
    doc.closeAllPreviews();
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
            onOpenSource={bridge.handleOpenSource}
            onJumpToConversation={handleJumpToConversation}
            pendingJump={conversation.pendingJump}
            onJumpHandled={conversation.clearPendingJump}
            docTrayItems={composer.items}
            primaryDocPath={composer.primaryPath}
            documentPaths={composer.documentPaths}
            docContextItems={composer.docContextItems}
            onTraySetPrimary={bridge.handleTraySetPrimary}
            onTrayRemove={bridge.handleTrayRemove}
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
              onPin={bridge.handlePinDoc}
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
              onUnpin={bridge.handleUnpinDoc}
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
            <SettingsPanel
              open={settingsOpen}
              onClose={() => setSettingsOpen(false)}
              onOpenConversation={(id) => {
                setSettingsOpen(false);
                conversation.selectConversation(id);
              }}
            />
            <SkillPickModal
              open={skillPick !== null}
              folderLabel={skillPick?.folder ?? ""}
              candidates={skillPick?.candidates ?? []}
              maxSelectable={composer.trayRemaining}
              onConfirm={handleSkillPickConfirm}
              onCancel={cancelSkillPick}
            />
          </>
        }
      />
    </DocPreviewProvider>
  );
}
