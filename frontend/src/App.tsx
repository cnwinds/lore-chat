import { useEffect, useRef, useState } from "react";
import {
  getAuthStatus,
  postGuestSession,
  type SourceRef,
  type SettingsAttention,
} from "./api";
import {
  DEFAULT_CAPABILITY,
  DemoCapabilityContext,
  resolveDemoCapability,
  type DemoCapability,
} from "./hooks/useDemoCapability";
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
import { useLlmSetupGuide } from "./hooks/app/useLlmSetupGuide";
import { useSettingsAttention } from "./hooks/app/useSettingsAttention";
import { useComposerDocState } from "./hooks/useComposerDocState";
import { useComposerPreviewBridge } from "./hooks/useComposerPreviewBridge";
import { useEnabledSkillsAttach } from "./hooks/useEnabledSkillsAttach";
import type { JumpTarget } from "./hooks/chat/useConversationJump";
import { MediaGalleryFloatLayer } from "./components/app/MediaGalleryFloatLayer";
import { MemoryFloatLayer } from "./components/app/MemoryFloatLayer";
import { SkillPickModal } from "./components/SkillPickModal";

type Gate = "loading" | "setup" | "login" | "app";

export default function App() {
  const [gate, setGate] = useState<Gate>("loading");
  const [capability, setCapability] = useState<DemoCapability>(DEFAULT_CAPABILITY);

  useEffect(() => {
    getAuthStatus()
      .then(async (s) => {
        if (s.demo && s.role !== "admin") {
          const issued = s.role === "guest" ? s : { ...s, role: "guest" as const };
          if (s.role !== "guest") await postGuestSession();
          setCapability(resolveDemoCapability(issued));
          setGate("app");
          return;
        }
        setCapability(resolveDemoCapability(s));
        if (s.setup_required) setGate("setup");
        else if (!s.authenticated) setGate("login");
        else setGate("app");
      })
      .catch(() => setGate("login"));
  }, []);

  const capabilityRef = useRef(capability);
  capabilityRef.current = capability;

  useEffect(() => {
    const onUnauthorized = () => {
      const cap = capabilityRef.current;
      // 演示访客 cookie 过期时重新签发，勿踢回登录页
      if (cap.isDemo && !cap.canWrite) {
        void postGuestSession()
          .then(() => getAuthStatus())
          .then((s) => {
            setCapability(resolveDemoCapability(s));
            setGate("app");
          })
          .catch(() => setGate("login"));
        return;
      }
      setGate("login");
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, []);

  if (gate === "loading") return null;
  if (gate === "setup")
    return (
      <SetupPage
        onDone={async () => {
          const s = await getAuthStatus();
          setCapability(resolveDemoCapability(s));
          setGate("app");
        }}
      />
    );
  if (gate === "login")
    return (
      <LoginPage
        onDone={async () => {
          const s = await getAuthStatus();
          setCapability(resolveDemoCapability(s));
          setGate("app");
        }}
      />
    );
  return (
    <DemoCapabilityContext.Provider value={capability}>
      <AppMain />
    </DemoCapabilityContext.Provider>
  );
}

function AppMain() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [kbPaths, setKbPaths] = useState<string[]>([]);
  const {
    settingsOpen,
    setSettingsOpen,
    llmSetupGuide,
    clearLlmSetupGuide,
  } = useLlmSetupGuide();
  const { attention, refreshAttention } = useSettingsAttention();
  const [liveAttention, setLiveAttention] = useState<SettingsAttention | null>(
    null,
  );
  useEffect(() => {
    refreshAttention();
  }, [settingsOpen, refreshAttention]);
  const displayAttention = liveAttention ?? attention;
  const [snippetSource, setSnippetSource] = useState<Extract<
    SourceRef,
    { type: "search" }
  > | null>(null);

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const doc = useDocPreviewLayout(refreshSidebar);
  const composer = useComposerDocState();
  const {
    skillPick,
    saving: skillPickSaving,
    openEnabledSkillsModal,
    handleSkillPickConfirm,
    cancelSkillPick,
  } = useEnabledSkillsAttach();
  const bridge = useComposerPreviewBridge({
    composer,
    doc,
    refreshSidebar,
    onOpenEnabledSkills: openEnabledSkillsModal,
    onSearchSource: setSnippetSource,
  });

  const conversation = useConversationShell({
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    composerPrimaryPath: composer.primaryPath,
    onSelectFile: bridge.handleSelectFile,
    onSelectFolder: bridge.handleSelectFolder,
    onOpenEnabledSkills: openEnabledSkillsModal,
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
          settingsAttention:
            displayAttention.model.any || displayAttention.usage.any,
          memoryAttention: displayAttention.memory.any,
          onDocsChange: setKbPaths,
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
            docContextItems={composer.docContextItems}
            onTraySetPrimary={bridge.handleTraySetPrimary}
            onTrayRemove={bridge.handleTrayRemove}
          />
        }
        docFloat={
          doc.showMemoryPanel ? (
            <MemoryFloatLayer
              docWidth={doc.floatWidth}
              onClose={doc.closeMemoryPanel}
              onToggleWidth={doc.toggleFloatWidth}
              onAttentionChange={refreshAttention}
              onOpenConversation={(id) => {
                doc.closeMemoryPanel();
                conversation.selectConversation(id, { keepPreviews: true });
              }}
            />
          ) : doc.showMediaGallery ? (
            <MediaGalleryFloatLayer
              directory={doc.mediaFolderPath!}
              refreshKey={doc.mediaRefreshKey}
              paths={kbPaths}
              docWidth={doc.floatWidth}
              onClose={doc.closeMediaFolder}
              onToggleWidth={doc.toggleFloatWidth}
            />
          ) : doc.showFloat ? (
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
              onClose={() => {
                setSettingsOpen(false);
                clearLlmSetupGuide();
                setLiveAttention(null);
                refreshAttention();
              }}
              showLlmSetupGuide={llmSetupGuide}
              onLlmConfigured={clearLlmSetupGuide}
              attention={attention}
              onAttentionChange={refreshAttention}
              onLiveAttentionChange={setLiveAttention}
            />
            <SkillPickModal
              open={skillPick !== null}
              candidates={skillPick?.candidates ?? []}
              initiallySelected={skillPick?.initiallySelected ?? []}
              saving={skillPickSaving}
              onConfirm={handleSkillPickConfirm}
              onCancel={cancelSkillPick}
            />
            {bridge.imageLightbox}
          </>
        }
      />
    </DocPreviewProvider>
  );
}
