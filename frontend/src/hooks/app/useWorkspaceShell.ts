import { useCallback, useEffect, useMemo, useState } from "react";
import type { SettingsAttention } from "../../api";
import type { ShareLinkModalTarget } from "../../components/share/ShareLinkModal";
import type { useConversationShell } from "./useConversationShell";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";

type ConversationShell = ReturnType<typeof useConversationShell>;
type DocLayout = ReturnType<typeof useDocPreviewLayout>;

type Options = {
  conversation: ConversationShell;
  doc: DocLayout;
  mobileLayout: boolean;
  displayAttention: SettingsAttention;
  setSettingsOpen: (open: boolean) => void;
  setShareTarget: (target: ShareLinkModalTarget | null) => void;
  setKbPaths: (paths: string[]) => void;
};

/** App 主布局：移动端导航、侧栏 props 与标题等 shell 接线。 */
export function useWorkspaceShell({
  conversation,
  doc,
  mobileLayout,
  displayAttention,
  setSettingsOpen,
  setShareTarget,
  setKbPaths,
}: Options) {
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
      onSearchHit: base.onSearchHit
        ? wrapClose(base.onSearchHit)
        : undefined,
      onSelectRole: base.onSelectRole
        ? wrapClose(base.onSelectRole)
        : undefined,
      onAddRole: base.onAddRole ? wrapClose(base.onAddRole) : undefined,
      onEditRole: base.onEditRole ? wrapClose(base.onEditRole) : undefined,
      onSelectFile: wrapClose(base.onSelectFile),
      onSelectFolder: base.onSelectFolder
        ? wrapClose(base.onSelectFolder)
        : undefined,
      onNewChat: base.onNewChat ? wrapClose(base.onNewChat) : undefined,
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
    setSettingsOpen,
    setShareTarget,
    setKbPaths,
  ]);

  const mobileHeaderTitle = useMemo(() => {
    const roles = conversation.roles ?? [];
    if (roles.length > 1 && conversation.activeRole) {
      return conversation.activeRole.name;
    }
    const id = conversation.activeConversationId;
    if (!id) return "新话题";
    return conversation.titleOverrides[id] || "对话";
  }, [
    conversation.roles,
    conversation.activeRole,
    conversation.activeConversationId,
    conversation.titleOverrides,
  ]);

  return {
    mobileNavOpen,
    openMobileNav: () => setMobileNavOpen(true),
    closeMobileNav,
    sidebarProps,
    mobileHeaderTitle,
  };
}