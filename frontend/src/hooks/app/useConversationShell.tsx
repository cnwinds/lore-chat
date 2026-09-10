import { useEffect, useMemo, useRef, useState } from "react";
import {
  createRole,
  deleteRole,
  ensureRoleActive,
  getConversation,
  getRoleTimeline,
  listBusyRoles,
  listRoles,
  openRoleNewTopic,
  type RoleSummary,
} from "../../api";
import { Sidebar } from "../../components/Sidebar";
import { RoleSettingsModal } from "../../components/RoleSettingsModal";
import { CreateRoleModal } from "../../components/role/CreateRoleModal";
import type { ComponentProps, ReactNode } from "react";
import type { useDocPreviewLayout } from "./useDocPreviewLayout";
import type { JumpTarget } from "../chat/useConversationJump";
import { MEMORY_DIR } from "../../utils/fileTree";
import { avatarStorageRef } from "../../utils/kbImageUrls";

const ACTIVE_ROLE_KEY = "lorechat.activeRoleId";

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
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [activeRoleId, setActiveRoleId] = useState<string | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
  const [titleOverrides, setTitleOverrides] = useState<Record<string, string>>(
    {},
  );
  const [pendingJump, setPendingJump] = useState<JumpTarget | null>(null);
  const [settingsRoleId, setSettingsRoleId] = useState<string | null>(null);
  const [busyRoleIds, setBusyRoleIds] = useState<string[]>([]);
  const [timelineRefreshKey, setTimelineRefreshKey] = useState(0);
  const sidebarLocateKbPathRef = useRef<((path: string) => void) | null>(null);
  const bootstrappedRef = useRef(false);
  const roleSwitchGenRef = useRef(0);
  const activeRoleIdRef = useRef<string | null>(null);
  const rolesRef = useRef<RoleSummary[]>([]);
  activeRoleIdRef.current = activeRoleId;
  rolesRef.current = roles;

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

  async function refreshRoles() {
    const { roles: next } = await listRoles();
    setRoles(next);
    return next;
  }

  async function activateRole(roleId: string, opts?: { keepPreviews?: boolean }) {
    const gen = ++roleSwitchGenRef.current;
    const prevRoleId = activeRoleId;
    try {
      const tl = await getRoleTimeline(roleId, {
        includeMessages: false,
        limit: 0,
      });
      if (gen !== roleSwitchGenRef.current) return;
      setActiveRoleId(roleId);
      try {
        localStorage.setItem(ACTIVE_ROLE_KEY, roleId);
      } catch {
        /* ignore */
      }
      setActiveConversationId(tl.tip_conversation_id);
      setTimelineRefreshKey((k) => k + 1);
      if (!opts?.keepPreviews) doc.closeAllPreviews();
      refreshSidebar();
    } catch (e) {
      // timeline 失败时回退 ensure-active
      try {
        const { conversation_id } = await ensureRoleActive(roleId);
        if (gen !== roleSwitchGenRef.current) return;
        setActiveRoleId(roleId);
        try {
          localStorage.setItem(ACTIVE_ROLE_KEY, roleId);
        } catch {
          /* ignore */
        }
        setActiveConversationId(conversation_id);
        setTimelineRefreshKey((k) => k + 1);
        if (!opts?.keepPreviews) doc.closeAllPreviews();
        refreshSidebar();
        return;
      } catch {
        /* fall through */
      }
      if (gen !== roleSwitchGenRef.current) return;
      // 勿回滚到已删除角色（删角色与切角色竞态时 prev 可能已失效）
      if (
        prevRoleId &&
        rolesRef.current.some((r) => r.id === prevRoleId)
      ) {
        setActiveRoleId(prevRoleId);
      } else if (
        activeRoleIdRef.current &&
        !rolesRef.current.some((r) => r.id === activeRoleIdRef.current)
      ) {
        setActiveRoleId(null);
        setActiveConversationId(null);
      }
      throw e;
    }
  }

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    void (async () => {
      try {
        const next = await refreshRoles();
        if (next.length === 0) return;
        let preferred: string | null = null;
        try {
          preferred = localStorage.getItem(ACTIVE_ROLE_KEY);
        } catch {
          preferred = null;
        }
        const match =
          (preferred && next.find((r) => r.id === preferred)) ||
          next.find((r) => r.is_default) ||
          next[0];
        await activateRole(match.id, { keepPreviews: true });
      } catch {
        /* 未登录等：保持空态 */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅启动一次
  }, []);

  useEffect(() => {
    if (sidebarRefreshKey === 0) return;
    void refreshRoles().catch(() => undefined);
  }, [sidebarRefreshKey]);

  useEffect(() => {
    if (roles.length < 2) {
      setBusyRoleIds([]);
      return;
    }
    let cancelled = false;
    async function poll() {
      try {
        const { role_ids } = await listBusyRoles();
        if (!cancelled) setBusyRoleIds(role_ids);
      } catch {
        if (!cancelled) setBusyRoleIds([]);
      }
    }
    void poll();
    const t = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [roles.length, sidebarRefreshKey]);

  async function newChat() {
    const roleId =
      activeRoleId ||
      roles.find((r) => r.is_default)?.id ||
      roles[0]?.id ||
      null;
    if (!roleId) {
      setActiveConversationId(null);
      return;
    }
    const gen = ++roleSwitchGenRef.current;
    try {
      const { conversation_id } = await openRoleNewTopic(roleId);
      if (gen !== roleSwitchGenRef.current) return;
      setActiveConversationId(conversation_id);
      setTimelineRefreshKey((k) => k + 1);
      refreshSidebar();
    } catch {
      if (gen !== roleSwitchGenRef.current) return;
      setActiveConversationId(null);
    }
  }

  async function acceptCreatedConversation(id: string) {
    const gen = roleSwitchGenRef.current;
    try {
      const conv = await getConversation(id);
      if (gen !== roleSwitchGenRef.current) return;
      if (
        conv.role_id &&
        activeRoleIdRef.current &&
        conv.role_id !== activeRoleIdRef.current
      ) {
        return;
      }
    } catch {
      if (gen !== roleSwitchGenRef.current) return;
    }
    if (gen !== roleSwitchGenRef.current) return;
    setActiveConversationId(id);
    refreshSidebar();
  }

  function selectConversation(id: string, opts?: { keepPreviews?: boolean }) {
    void openConversation(id, opts);
  }

  async function openConversation(
    id: string,
    opts?: { keepPreviews?: boolean },
  ) {
    const gen = ++roleSwitchGenRef.current;
    try {
      const conv = await getConversation(id);
      if (gen !== roleSwitchGenRef.current) return;
      const rid = conv.role_id;
      if (rid) {
        setActiveRoleId(rid);
        try {
          localStorage.setItem(ACTIVE_ROLE_KEY, rid);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* 仍打开会话 id；角色保持现状 */
    }
    if (gen !== roleSwitchGenRef.current) return;
    setActiveConversationId(id);
    setTimelineRefreshKey((k) => k + 1);
    if (!opts?.keepPreviews) doc.closeAllPreviews();
  }

  async function selectRole(roleId: string) {
    try {
      await activateRole(roleId);
    } catch {
      /* ensure 失败时 activateRole 已回滚角色 */
    }
  }

  const [showCreateRoleModal, setShowCreateRoleModal] = useState(false);

  function openCreateRoleModal() {
    setShowCreateRoleModal(true);
  }

  async function handleCreateRole(name: string, avatar: string) {
    setShowCreateRoleModal(false);
    try {
      const role = await createRole({
        name: name.trim(),
        avatar: avatarStorageRef(avatar),
      });
      await refreshRoles();
      await activateRole(role.id);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "创建角色失败");
    }
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

  const activeRole = useMemo(
    () => roles.find((r) => r.id === activeRoleId) ?? null,
    [roles, activeRoleId],
  );

  const settingsRole = useMemo(
    () => roles.find((r) => r.id === settingsRoleId) ?? null,
    [roles, settingsRoleId],
  );

  function handleDeleteConversation(id: string) {
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
  }

  const sidebarProps: ComponentProps<typeof Sidebar> = {
    refreshKey: sidebarRefreshKey,
    activePaths: kbTreeActivePaths,
    activeConversationId,
    activeRoleId,
    roles,
    titleOverrides,
    busyRoleIds,
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
    onSelectRole: (id) => {
      void selectRole(id);
    },
    onAddRole: () => {
      openCreateRoleModal();
    },
    onEditRole: (id) => {
      setSettingsRoleId(id);
    },
    onSelectConversation: selectConversation,
    onSearchHit: (hit) => {
      void (async () => {
        // 同角色时间线内：保持 tip，仅跳转定位
        if (hit.role_id && hit.role_id === activeRoleIdRef.current) {
          if (hit.message_id) {
            requestJump({
              conversationId: hit.conversation_id,
              messageId: hit.message_id,
            });
          } else {
            const el = document.querySelector(
              `[data-conversation-id="${hit.conversation_id}"]`,
            );
            el?.scrollIntoView({ behavior: "smooth", block: "start" });
          }
          return;
        }
        await openConversation(hit.conversation_id);
        if (hit.message_id) {
          requestJump({
            conversationId: hit.conversation_id,
            messageId: hit.message_id,
          });
        }
      })();
    },
    onDeleteConversation: handleDeleteConversation,
  };

  async function handleDeleteRole(roleId: string) {
    const deletedId = roleId;
    try {
      await deleteRole(deletedId);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "删除角色失败");
      return;
    }
    try {
      const next = await refreshRoles();
      roleRefreshAfterDelete(deletedId, next);
    } catch {
      if (activeRoleIdRef.current === deletedId) {
        setActiveRoleId(null);
        setActiveConversationId(null);
      }
      refreshSidebar();
    }
  }

  function roleRefreshAfterDelete(
    deletedId: string,
    next: RoleSummary[],
  ) {
    setSettingsRoleId((cur) => (cur === deletedId ? null : cur));
    if (activeRoleIdRef.current !== deletedId) {
      refreshSidebar();
      return;
    }
    const fallback =
      next.find((r) => r.is_default)?.id || next[0]?.id || null;
    if (!fallback) {
      setActiveRoleId(null);
      setActiveConversationId(null);
      refreshSidebar();
      return;
    }
    const gen = ++roleSwitchGenRef.current;
    void (async () => {
      try {
        const { conversation_id } = await ensureRoleActive(fallback);
        if (gen !== roleSwitchGenRef.current) return;
        setActiveRoleId(fallback);
        try {
          localStorage.setItem(ACTIVE_ROLE_KEY, fallback);
        } catch {
          /* ignore */
        }
        setActiveConversationId(conversation_id);
        setTimelineRefreshKey((k) => k + 1);
        doc.closeAllPreviews();
        refreshSidebar();
      } catch {
        if (gen !== roleSwitchGenRef.current) return;
        setActiveRoleId(fallback);
        try {
          localStorage.setItem(ACTIVE_ROLE_KEY, fallback);
        } catch {
          /* ignore */
        }
        setActiveConversationId(null);
        refreshSidebar();
      }
    })();
  }

  const roleOverlays: ReactNode = (
    <>
      {settingsRole && (
        <RoleSettingsModal
          role={settingsRole}
          open={!!settingsRoleId}
          onClose={() => setSettingsRoleId(null)}
          onSaved={(updated) => {
            setRoles((prev) =>
              prev.map((r) => (r.id === updated.id ? updated : r)),
            );
            refreshSidebar();
          }}
          onDeleted={() => {
            const deletedId = settingsRoleId;
            if (!deletedId) return;
            void refreshRoles()
              .then((next) => roleRefreshAfterDelete(deletedId, next))
              .catch(() => {
                if (activeRoleIdRef.current === deletedId) {
                  setActiveRoleId(null);
                  setActiveConversationId(null);
                }
                refreshSidebar();
              });
          }}
        />
      )}
      <CreateRoleModal
        open={showCreateRoleModal}
        onClose={() => setShowCreateRoleModal(false)}
        onConfirm={handleCreateRole}
      />
    </>
  );

  return {
    activeConversationId,
    setActiveConversationId,
    activeRoleId,
    activeRole,
    roles,
    titleOverrides,
    setTitleOverrides,
    sidebarProps,
    roleOverlays,
    selectConversation,
    openConversation,
    acceptCreatedConversation,
    pendingJump,
    requestJump,
    clearPendingJump,
    locateKbPathInTree,
    timelineRefreshKey,
    handleDeleteRole,
  };
}
