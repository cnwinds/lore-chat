import { useCallback, useEffect, useState } from "react";
import { getAuthStatus, getConversation, type SourceRef, type SettingsAttention } from "./api";
import type { RoomSummary } from "./types/chat";
import { LoginPage } from "./components/auth/LoginPage";
import { SetupPage } from "./components/auth/SetupPage";
import { Chat } from "./components/Chat";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { SettingsPanel, type SettingsTab } from "./components/settings/SettingsPanel";
import { ShareLinkModal, type ShareLinkModalTarget } from "./components/share/ShareLinkModal";
import { SharePage } from "./pages/SharePage";
import { parseSharePathname } from "./api/share";
import { AppShell } from "./components/app/AppShell";
import { ChannelFloatLayer } from "./components/app/ChannelFloatLayer";
import { DocFloatLayer } from "./components/app/DocFloatLayer";
import { DocPinnedPanel } from "./components/app/DocPinnedPanel";
import { DocPreviewProvider } from "./contexts/DocPreviewContext";
import { buildDocViewerHandlers } from "./hooks/app/buildDocViewerHandlers";
import { useAppEscapeKey } from "./hooks/app/useAppEscapeKey";
import { useConversationShell } from "./hooks/app/useConversationShell";
import { useDocPreviewLayout } from "./hooks/app/useDocPreviewLayout";
import { useLlmSetupGuide } from "./hooks/app/useLlmSetupGuide";
import { useSettingsAttention } from "./hooks/app/useSettingsAttention";
import { useRoleShell } from "./hooks/app/useRoleShell";
import { useComposerDocState } from "./hooks/useComposerDocState";
import { useComposerPreviewBridge } from "./hooks/useComposerPreviewBridge";
import { useEnabledSkillsAttach } from "./hooks/useEnabledSkillsAttach";
import type { JumpTarget } from "./hooks/chat/useConversationJump";
import { MediaGalleryFloatLayer } from "./components/app/MediaGalleryFloatLayer";
import { MemoryFloatLayer } from "./components/app/MemoryFloatLayer";
import { SkillPickModal } from "./components/SkillPickModal";
import { useWorkspaceShell } from "./hooks/app/useWorkspaceShell";
import { useMobileLayout } from "./hooks/useMobileLayout";
import { MEMORY_DIR } from "./utils/fileTree";

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
  const [groupEditKey, setGroupEditKey] = useState(0);

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const doc = useDocPreviewLayout(refreshSidebar);
  const composer = useComposerDocState();
  const role = useRoleShell();
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
    void (async () => {
      // 同角色时间线：不切 tip，仅滚动定位
      if (
        conversation.activeRoleId &&
        conversation.activeConversationId &&
        target.conversationId !== conversation.activeConversationId
      ) {
        try {
          const conv = await getConversation(target.conversationId);
          const kind = conv.kind || "owner_dm";
          const parts = conv.participant_role_ids || [];
          if (
            kind !== "group" &&
            (conv.role_id === conversation.activeRoleId ||
              (conversation.activeRoleId &&
                parts.includes(conversation.activeRoleId)))
          ) {
            conversation.requestJump(target);
            doc.closeAllPreviews();
            return;
          }
          if (kind === "group") {
            conversation.selectGroup(target.conversationId, conv.title);
            conversation.requestJump(target);
            doc.closeAllPreviews();
            return;
          }
        } catch {
          /* fall through to open */
        }
      }
      if (conversation.activeConversationId !== target.conversationId) {
        await conversation.openConversation(target.conversationId);
      }
      conversation.requestJump(target);
      doc.closeAllPreviews();
    })();
  }

  const floatDocHandlers = buildDocViewerHandlers(
    doc,
    "float",
    (id) => {
      void conversation.openConversation(id);
    },
    conversation.locateKbPathInTree,
    (path, title) =>
      setShareTarget({ type: "doc", path, defaultTitle: title }),
  );
  const pinnedDocHandlers = buildDocViewerHandlers(
    doc,
    "pinned",
    (id) => {
      void conversation.openConversation(id);
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
  const {
    mobileNavOpen,
    openMobileNav,
    closeMobileNav,
    mobileHeaderTitle,
  } = useWorkspaceShell({
    conversation,
    doc,
    mobileLayout,
    displayAttention,
    setSettingsOpen,
    setShareTarget,
    setKbPaths,
  });

  // 角色列表与会话壳同步：列表高亮跟 conversation；配置面板跟同一 id
  useEffect(() => {
    if (conversation.activeRoleId) {
      role.setActiveRoleId(conversation.activeRoleId);
    }
  }, [conversation.activeRoleId, role.setActiveRoleId]);

  // Build KB sidebar active paths
  const kbActivePaths = [
    doc.pinnedPath,
    doc.floatPath,
    doc.mediaFolderPath,
    doc.memoryPanelOpen ? MEMORY_DIR : null,
    composer.primaryPath,
  ].filter((p): p is string => Boolean(p));

  function openGroupSettings(room?: RoomSummary) {
    if (room) void conversation.selectGroup(room.id, room);
    role.expandConfigPanel();
    setGroupEditKey((k) => k + 1);
    closeMobileNav();
  }

  return (
    <DocPreviewProvider value={doc.contextValue}>
      <AppShell
        panelFocus={Boolean(doc.panelFocus)}
        floatFocus={Boolean(doc.floatFocus)}
        hasMergeReview={false}
        mainFloatWide={doc.mainFloatWide}
        configMode={conversation.activeGroupId ? "group" : "role"}
        mobileLayout={mobileLayout}
        mobileNavOpen={mobileNavOpen}
        onMobileNavClose={closeMobileNav}
        settingsAttention={displayAttention.any}
        onOpenSettings={() => {
          setSettingsOpen(true);
          closeMobileNav();
        }}
        channelsOpen={doc.showChannelPanel}
        onToggleChannels={() => {
          doc.openChannelPanel();
          closeMobileNav();
        }}
        roleListProps={{
          activeRoleId: conversation.activeGroupId
            ? null
            : conversation.activeRoleId || role.activeRoleId,
          activeGroupId: conversation.activeGroupId,
          onSelectRole: (id) => {
            role.setActiveRoleId(id);
            void conversation.sidebarProps.onSelectRole?.(id);
          },
          onSelectGroup: (id, room) => conversation.selectGroup(id, room),
          onNewRole: () => {
            void conversation.sidebarProps.onAddRole?.();
            role.refreshRoles();
            refreshSidebar();
          },
          onNewGroup: conversation.openCreateGroupModal,
          onEditGroup: (room) => openGroupSettings(room),
          onDeleteGroup: (room) => conversation.deleteGroup(room),
          onSearchHit: (hit) => {
            conversation.sidebarProps.onSearchHit?.(hit);
          },
          onSelectFile: (path) => {
            bridge.handleSelectFile(path);
          },
          onDeleteRole: (r) => {
            void (async () => {
              await conversation.handleDeleteRole(r.id);
              role.refreshRoles();
              refreshSidebar();
            })();
          },
          busyRoleIds: conversation.sidebarProps.busyRoleIds,
          refreshKey:
            role.roleRefreshKey +
            sidebarRefreshKey +
            conversation.groupRefreshKey,
        }}
        kbSidebarProps={{
          refreshKey: sidebarRefreshKey,
          activePaths: kbActivePaths,
          memoryAttention: displayAttention.memory.any,
          onSelectFile: bridge.handleSelectFile,
          onSelectFolder: bridge.handleSelectFolder,
          onOpenEnabledSkills: openEnabledSkillsModal,
          onKbPathChanged: bridge.handleKbPathChanged,
          onKbPathsDeleted: bridge.handleKbPathsDeleted,
          onDocsChange: setKbPaths,
          onBindLocateKbPath: (locate) => {
            conversation.locateKbPathInTree = locate ?? (() => {});
          },
        }}
        roleConfigPanelProps={{
          roleId: conversation.activeRoleId || role.activeRoleId,
          collapsed: role.configPanelCollapsed,
          onToggleCollapsed: role.toggleConfigPanel,
          onRoleUpdated: role.refreshRoles,
        }}
        groupConfigPanelProps={{
          roomId: conversation.activeGroupId,
          roles: conversation.roles,
          seed: conversation.activeGroupId
            ? {
                title: conversation.activeGroupTitle,
                avatar: conversation.activeGroupAvatar,
                participants: conversation.activeGroupParticipants,
                participant_role_ids: conversation.activeGroupParticipants.map(
                  (p) => p.id,
                ),
              }
            : null,
          collapsed: role.configPanelCollapsed,
          onToggleCollapsed: role.toggleConfigPanel,
          editRequestKey: groupEditKey,
          onSaved: conversation.syncActiveGroup,
          onDeleted: (id) => {
            void conversation.deleteGroup({
              id,
              title: conversation.activeGroupTitle || "群聊",
              kind: "group",
              avatar: conversation.activeGroupAvatar,
              participant_role_ids: conversation.activeGroupParticipants.map(
                (p) => p.id,
              ),
              participants: conversation.activeGroupParticipants,
            });
          },
        }}
        chat={
          <Chat
            conversationId={conversation.activeConversationId}
            roleId={conversation.activeRoleId}
            roles={conversation.roles}
            timelineRefreshKey={conversation.timelineRefreshKey}
            roleConfigCollapsed={role.configPanelCollapsed}
            onToggleRoleConfig={role.toggleConfigPanel}
            onSelectRole={(id) => {
              void conversation.sidebarProps.onSelectRole?.(id);
            }}
            roomMode={conversation.activeGroupId ? "group" : "role"}
            roomTitle={conversation.activeGroupTitle}
            roomAvatar={conversation.activeGroupAvatar}
            roomParticipants={conversation.activeGroupParticipants}
            onRoomInterjectSent={conversation.bumpTimeline}
            onOpenGroup={(id) => conversation.selectGroup(id)}
            mobileLayout={mobileLayout}
            mobileHeaderTitle={mobileHeaderTitle}
            onOpenMobileNav={openMobileNav}
            onConversationRoleMismatch={(cid, roleId) => {
              if (conversation.activeConversationId !== cid) return;
              void conversation.selectRole(roleId);
            }}
            onConversationCreated={(id) => {
              void conversation.acceptCreatedConversation(id);
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
                void conversation.openConversation(id, {
                  keepPreviews: true,
                });
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
          ) : doc.showChannelPanel ? (
            <ChannelFloatLayer
              docWidth={doc.floatWidth}
              onClose={doc.closeChannelPanel}
              onToggleWidth={doc.toggleFloatWidth}
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
            {conversation.roleOverlays}
            {bridge.imageLightbox}
          </>
        }
      />
    </DocPreviewProvider>
  );
}
