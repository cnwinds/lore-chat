import { useCallback, useEffect, useMemo, useState } from "react";
import { getAuthStatus, type SourceRef, type SettingsAttention } from "./api";
import { LoginPage } from "./components/auth/LoginPage";
import { SetupPage } from "./components/auth/SetupPage";
import { Chat } from "./components/Chat";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { SettingsPanel, type SettingsTab } from "./components/settings/SettingsPanel";
import { ShareLinkModal, type ShareLinkModalTarget } from "./components/share/ShareLinkModal";
import { SharePage } from "./pages/SharePage";
import { parseSharePathname } from "./api/share";
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
import { useMobileLayout } from "./hooks/useMobileLayout";

type Gate = "loading" | "setup" | "login" | "app";

export default function App() {
  const shareId = parseSharePathname(window.location.pathname);
  if (shareId) {
    return <SharePage shareId={shareId} />;
  }
  return <AppGate />;
}

function AppGate() {
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
  const [kbPaths, setKbPaths] = useState<string[]>([]);
  const [shareTarget, setShareTarget] = useState<ShareLinkModalTarget | null>(null);
  const [settingsNavigateTab, setSettingsNavigateTab] = useState<SettingsTab | null>(null);
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

  const floatDocHandlers = buildDocViewerHandlers(
    doc,
    "float",
    (id) => {
      conversation.setActiveConversationId(id);
      doc.closeAllPreviews();
    },
    conversation.locateKbPathInTree,
    (path, title) =>
      setShareTarget({ type: "doc", path, defaultTitle: title }),
  );
  const pinnedDocHandlers = buildDocViewerHandlers(
    doc,
    "pinned",
    (id) => {
      conversation.setActiveConversationId(id);
      doc.closeAllPreviews();
    },
    conversation.locateKbPathInTree,
    (path, title) =>
      setShareTarget({ type: "doc", path, defaultTitle: title }),
  );

  const closeShareModal = useCallback(() => setShareTarget(null), []);

  const navigateSettingsTab = useCallback((tab: SettingsTab) => {
    try {
      localStorage.setItem("lorechat.settingsTab", tab);
    } catch {
      /* ignore */
    }
    setSettingsNavigateTab(tab);
    setSettingsOpen(true);
  }, [setSettingsOpen]);

  const closeShareAndOpenSettings = useCallback(
    (tab: SettingsTab) => {
      setShareTarget(null);
      navigateSettingsTab(tab);
    },
    [navigateSettingsTab],
  );

  const handleSettingsNavigateHandled = useCallback(() => {
    setSettingsNavigateTab(null);
  }, []);

  const mobileLayout = useMobileLayout();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  useEffect(() => {
    if (!mobileLayout || !mobileNavOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileLayout, mobileNavOpen]);

  useEffect(() => {
    if (!mobileLayout) setMobileNavOpen(false);
  }, [mobileLayout]);

  useEffect(() => {
    if (!mobileLayout) return;
    if (
      doc.showFloat ||
      doc.showPinned ||
      doc.showMemoryPanel ||
      doc.showMediaGallery
    ) {
      setMobileNavOpen(false);
    }
  }, [
    mobileLayout,
    doc.showFloat,
    doc.showPinned,
    doc.showMemoryPanel,
    doc.showMediaGallery,
  ]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      closeMobileNav();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen, closeMobileNav]);

  const sidebarProps = useMemo(() => {
    const base = conversation.sidebarProps;
    const wrapClose = <A extends unknown[]>(fn: (...args: A) => void) =>
      (...args: A) => {
        fn(...args);
        if (mobileLayout) closeMobileNav();
      };
    return {
      ...base,
      collapsed: mobileLayout ? false : base.collapsed,
      onToggleCollapsed: mobileLayout ? undefined : base.onToggleCollapsed,
      onSelectConversation: wrapClose(base.onSelectConversation),
      onSelectFile: wrapClose(base.onSelectFile),
      onSelectFolder: base.onSelectFolder
        ? wrapClose(base.onSelectFolder)
        : undefined,
      onNewChat: wrapClose(base.onNewChat),
      onOpenSettings: () => {
        setSettingsOpen(true);
        closeMobileNav();
      },
      onShareConversation: (id: string, title: string) => {
        setShareTarget({
          type: "conversation",
          conversationId: id,
          defaultTitle: title,
        });
        closeMobileNav();
      },
      settingsAttention:
        displayAttention.model.any || displayAttention.usage.any,
      memoryAttention: displayAttention.memory.any,
      onDocsChange: setKbPaths,
    };
  }, [
    conversation.sidebarProps,
    mobileLayout,
    closeMobileNav,
    displayAttention.model.any,
    displayAttention.usage.any,
    displayAttention.memory.any,
  ]);

  const mobileHeaderTitle = useMemo(() => {
    const id = conversation.activeConversationId;
    if (!id) return "新对话";
    return conversation.titleOverrides[id] || "对话";
  }, [conversation.activeConversationId, conversation.titleOverrides]);

  return (
    <DocPreviewProvider value={doc.contextValue}>
      <AppShell
        panelFocus={Boolean(doc.panelFocus)}
        floatFocus={Boolean(doc.floatFocus)}
        hasMergeReview={false}
        mainFloatWide={doc.mainFloatWide}
        mobileLayout={mobileLayout}
        mobileNavOpen={mobileNavOpen}
        onMobileNavClose={closeMobileNav}
        sidebarProps={sidebarProps}
        chat={
          <Chat
            conversationId={conversation.activeConversationId}
            mobileLayout={mobileLayout}
            mobileHeaderTitle={mobileHeaderTitle}
            onOpenMobileNav={() => setMobileNavOpen(true)}
            onMobileNewChat={() => sidebarProps.onNewChat()}
            onConversationCreated={(id) => {
              conversation.setActiveConversationId(id);
              refreshSidebar();
            }}
            onFirstQuestionTitle={(id, title) =>
              conversation.setTitleOverrides((prev) => ({ ...prev, [id]: title }))
            }
            onSidebarRefresh={refreshSidebar}
            onOpenSource={bridge.handleOpenSource}
            onJumpToConversation={(target) => {
              handleJumpToConversation(target);
              closeMobileNav();
            }}
            pendingJump={conversation.pendingJump}
            onJumpHandled={conversation.clearPendingJump}
            docTrayItems={composer.items}
            primaryDocPath={composer.primaryPath}
            docContextItems={composer.docContextItems}
            onTraySetPrimary={bridge.handleTraySetPrimary}
            onTrayRemove={bridge.handleTrayRemove}
            onShareConversation={
              conversation.activeConversationId
                ? () =>
                    setShareTarget({
                      type: "conversation",
                      conversationId: conversation.activeConversationId!,
                      defaultTitle:
                        conversation.titleOverrides[
                          conversation.activeConversationId!
                        ] || "对话分享",
                    })
                : undefined
            }
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
              navigateToTab={settingsNavigateTab}
              onNavigateToTabHandled={handleSettingsNavigateHandled}
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
            <ShareLinkModal
              open={shareTarget !== null}
              target={shareTarget}
              onClose={closeShareModal}
              onOpenShareSettings={() => closeShareAndOpenSettings("share")}
              onOpenModelSettings={() => closeShareAndOpenSettings("model")}
            />
            {bridge.imageLightbox}
          </>
        }
      />
    </DocPreviewProvider>
  );
}
