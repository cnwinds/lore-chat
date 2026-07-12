import { useState } from "react";
import {
  createConversation,
  listConversations,
} from "../../api";
import { Sidebar } from "../../components/Sidebar";
import type { ComponentProps } from "react";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type DocPreview = ReturnType<typeof useDocPreviewLayout>;

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

type Options = {
  sidebarRefreshKey: number;
  refreshSidebar: () => void;
  doc: DocPreview;
  composerPrimaryPath: string | null;
  onSelectFile: (path: string, mods?: SelectMods) => void;
};

export function useConversationShell({
  sidebarRefreshKey,
  refreshSidebar,
  doc,
  composerPrimaryPath,
  onSelectFile,
}: Options) {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
  const [titleOverrides, setTitleOverrides] = useState<Record<string, string>>(
    {},
  );

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
    doc.requestCloseDocPreview();
  }

  const sidebarProps: ComponentProps<typeof Sidebar> = {
    refreshKey: sidebarRefreshKey,
    selectedPath: composerPrimaryPath ?? doc.previewPath,
    activeConversationId,
    titleOverrides,
    collapsed: doc.docFocus && doc.previewPath ? doc.sidebarCollapsed : false,
    onToggleCollapsed:
      doc.docFocus && doc.previewPath
        ? () => doc.setSidebarCollapsed((c) => !c)
        : undefined,
    onSelectFile,
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
  };
}
