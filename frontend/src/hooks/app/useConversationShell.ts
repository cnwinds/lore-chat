import { useMemo, useRef, useState } from "react";
import {
  createConversation,
  listConversations,
} from "../../api";
import { Sidebar } from "../../components/Sidebar";
import type { ComponentProps } from "react";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";
import type { JumpTarget } from "../chat/useConversationJump";
import { MEMORY_DIR } from "../../utils/fileTree";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;

function treeActivePaths(
  doc: DocPreview,
  composerPrimaryPath: string | null,
): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const p of [
    doc.pinnedPath,
    doc.floatPath,
    doc.mediaFolderPath,
    doc.memoryPanelOpen ? MEMORY_DIR : null,
    composerPrimaryPath,
  ]) {
    if (p && !seen.has(p)) {
      seen.add(p);
      out.push(p);
    }
  }
  return out;
}

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean };

type Options = {
  sidebarRefreshKey: number;
  refreshSidebar: () => void;
  doc: DocPreview;
  composerPrimaryPath: string | null;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onSelectFolder?: (path: string, mods?: SelectMods) => void;
  onOpenEnabledSkills?: () => void;
  onKbPathChanged?: (from: string, to: string) => void;
  onKbPathsDeleted?: (paths: string[]) => void;
};

export function useConversationShell({
  sidebarRefreshKey,
  refreshSidebar,
  doc,
  composerPrimaryPath,
  onSelectFile,
  onSelectFolder,
  onOpenEnabledSkills,
  onKbPathChanged,
  onKbPathsDeleted,
}: Options) {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
  const [titleOverrides, setTitleOverrides] = useState<Record<string, string>>(
    {},
  );
  const [pendingJump, setPendingJump] = useState<JumpTarget | null>(null);
  const sidebarLocateKbPathRef = useRef<((path: string) => void) | null>(null);

  function locateKbPathInTree(path: string) {
    const shouldExpandSidebar =
      (doc.floatFocus || doc.pinnedFocus) &&
      (doc.floatPath || doc.pinnedPath) &&
      doc.sidebarCollapsed;
    const runLocate = () => sidebarLocateKbPathRef.current?.(path);
    if (shouldExpandSidebar) {
      doc.setSidebarCollapsed(false);
      requestAnimationFrame(() => {
        requestAnimationFrame(runLocate);
      });
    } else {
      runLocate();
    }
  }

  function requestJump(target: JumpTarget) {
    setPendingJump(target);
  }

  function clearPendingJump() {
    setPendingJump(null);
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

  function selectConversation(id: string, opts?: { keepPreviews?: boolean }) {
    setActiveConversationId(id);
    if (!opts?.keepPreviews) doc.closeAllPreviews();
  }

  const kbTreeActivePaths = useMemo(
    () => treeActivePaths(doc, composerPrimaryPath),
    [
      doc.pinnedPath,
      doc.floatPath,
      doc.mediaFolderPath,
      doc.memoryPanelOpen,
      composerPrimaryPath,
    ],
  );

  const sidebarProps: ComponentProps<typeof Sidebar> = {
    refreshKey: sidebarRefreshKey,
    activePaths: kbTreeActivePaths,
    activeConversationId,
    titleOverrides,
    collapsed:
      (doc.floatFocus || doc.pinnedFocus) && (doc.floatPath || doc.pinnedPath)
        ? doc.sidebarCollapsed
        : false,
    onToggleCollapsed:
      (doc.floatFocus || doc.pinnedFocus) && (doc.floatPath || doc.pinnedPath)
        ? () => doc.setSidebarCollapsed((c) => !c)
        : undefined,
    onSelectFile,
    onSelectFolder,
    onOpenEnabledSkills,
    onKbPathChanged,
    onKbPathsDeleted,
    onBindLocateKbPath: (locate) => {
      sidebarLocateKbPathRef.current = locate;
    },
    onNewChat: () => {
      void newChat();
    },
    onSelectConversation: selectConversation,
    onDeleteConversation: (id) => {
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
    },
  };

  return {
    activeConversationId,
    setActiveConversationId,
    titleOverrides,
    setTitleOverrides,
    sidebarProps,
    selectConversation,
    pendingJump,
    requestJump,
    clearPendingJump,
    locateKbPathInTree,
  };
}
