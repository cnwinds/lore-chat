import { useEffect, useRef, useState } from "react";
import { getAuthStatus, type SourceRef, isMarkdownPath, downloadUrl, discoverSkills } from "./api";
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
import { SkillPickModal } from "./components/SkillPickModal";
import { COMPOSER_TRAY_MAX } from "./types/composer";
import { isInsideSkillPackage } from "./utils/kbSkill";

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
  const [kbDocs, setKbDocs] = useState<string[]>([]);
  const [skillPick, setSkillPick] = useState<{
    folder: string;
    candidates: string[];
  } | null>(null);

  function addDocToComposer(path: string) {
    const title = path.split("/").pop() ?? path;
    if (!composer.items.some((i) => i.path === path)) {
      composer.addDocumentToTray(path, title);
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
    const wasInTray = composer.items.some((i) => i.path === path);
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
    if (!isMarkdownPath(path)) {
      window.open(downloadUrl(path), "_blank", "noopener,noreferrer");
      return;
    }
    if (mods?.ctrlKey || mods?.metaKey || mods?.shiftKey) {
      if (isInsideSkillPackage(path, kbDocs)) {
        window.alert("Skill 包内文档请点文件夹附加 Skill；此处仅可打开阅读。");
        return;
      }
      composer.addDocumentToTray(path, title);
    } else {
      doc.openDocPreview(path, undefined, { pin: false });
    }
  }

  function handleKbPathChanged(fromPath: string, toPath: string) {
    composer.remapPath(fromPath, toPath);
    doc.remapOpenPath(fromPath, toPath);
    refreshSidebar();
  }

  function addSkillsToTray(selected: string[]) {
    const room = composer.trayRemaining;
    if (room <= 0) {
      window.alert(`托盘已满（最多 ${COMPOSER_TRAY_MAX} 项）。`);
      return;
    }
    const toAdd = selected.slice(0, room);
    if (toAdd.length < selected.length) {
      window.alert(`托盘最多 ${COMPOSER_TRAY_MAX} 项，已加入前 ${toAdd.length} 个 Skill。`);
    }
    composer.addSkillRoots(toAdd);
  }

  function openSkillPickForFolder(folderPath: string) {
    void (async () => {
      try {
        const { roots } = await discoverSkills(folderPath);
        if (roots.length === 0) {
          window.alert(
            "该目录及子目录下未发现 Skill 包（每个包须为直接包含 SKILL.md 的文件夹）。",
          );
          return;
        }
        if (roots.length === 1) {
          addSkillsToTray(roots);
          return;
        }
        setSkillPick({ folder: folderPath, candidates: roots });
      } catch (err) {
        window.alert(err instanceof Error ? err.message : "发现 Skill 失败");
      }
    })();
  }

  function handleSelectFolder(path: string, mods?: { ctrlKey?: boolean; metaKey?: boolean }) {
    if (mods?.ctrlKey || mods?.metaKey) {
      openSkillPickForFolder(path);
    }
  }

  function handleSkillPickConfirm(selected: string[]) {
    addSkillsToTray(selected);
    setSkillPick(null);
  }

  function handleKbPathsDeleted(paths: string[]) {
    const deleted = new Set(paths);
    for (const p of composer.items.map((i) => i.path)) {
      if (deleted.has(p)) composer.removeFromTray(p);
    }
    if (doc.floatPath && deleted.has(doc.floatPath)) doc.closeFloatPreview();
    if (doc.pinnedPath && deleted.has(doc.pinnedPath)) doc.closePinnedPreview();
    refreshSidebar();
  }

  function handleTraySetPrimary(path: string) {
    const item = composer.items.find((i) => i.path === path);
    if (!item || item.kind !== "document") return;
    composer.setPrimary(path);
    openDocWithComposer(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    const wasPinned = doc.pinnedPath === path;
    composer.removeFromTray(path);
    if (wasPinned) doc.closePinnedPreview();
  }

  const conversation = useConversationShell({
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    composerPrimaryPath: composer.primaryPath,
    onSelectFile: handleSelectFile,
    onSelectFolder: handleSelectFolder,
    onAttachSkillsFolder: openSkillPickForFolder,
    onDocsLoaded: setKbDocs,
    onKbPathChanged: handleKbPathChanged,
    onKbPathsDeleted: handleKbPathsDeleted,
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
            documentPaths={composer.documentPaths}
            docContextItems={composer.docContextItems}
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
              onCancel={() => setSkillPick(null)}
            />
          </>
        }
      />
    </DocPreviewProvider>
  );
}
