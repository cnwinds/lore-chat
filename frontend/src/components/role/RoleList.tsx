import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import {
  listRoles,
  listRooms,
  type ConversationSearchHit,
  type Role,
  type RoomSummary,
} from "../../api";
import { formatRoleListTime } from "../../utils/displayTime";
import {
  buildInboxItems,
  groupReplyPreview,
  roleReplyPreview,
} from "../../utils/roleListPreview";
import { workspaceSearchHotkeyLabel } from "../../utils/workspaceSearch";
import { GlobalSearchPalette } from "./GlobalSearchPalette";
import { GroupAvatar } from "./GroupAvatar";
import { RoleAvatar } from "./RoleAvatar";

type InboxMenu =
  | { kind: "role"; role: Role; x: number; y: number }
  | { kind: "group"; room: RoomSummary; x: number; y: number };

type Props = {
  activeRoleId: string | null;
  activeGroupId?: string | null;
  onSelectRole: (roleId: string) => void;
  onSelectGroup?: (id: string, room?: RoomSummary) => void;
  onNewRole: () => void;
  onNewGroup?: () => void;
  onDeleteRole?: (role: Role) => void | Promise<void>;
  onEditGroup?: (room: RoomSummary) => void;
  onDeleteGroup?: (room: RoomSummary) => void | Promise<void>;
  onSearchHit?: (hit: ConversationSearchHit) => void;
  onSelectFile?: (path: string) => void;
  busyRoleIds?: string[];
  refreshKey?: number;
};

export function RoleList({
  activeRoleId,
  activeGroupId = null,
  onSelectRole,
  onSelectGroup,
  onNewRole,
  onNewGroup,
  onDeleteRole,
  onEditGroup,
  onDeleteGroup,
  onSearchHit,
  onSelectFile,
  busyRoleIds = [],
  refreshKey = 0,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [menu, setMenu] = useState<InboxMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const composeRef = useRef<HTMLDivElement>(null);
  const composeBtnRef = useRef<HTMLButtonElement>(null);
  const inbox = useMemo(
    () => buildInboxItems(roles, rooms, busyRoleIds),
    [roles, rooms, busyRoleIds],
  );
  const canCreateGroup = roles.length >= 2 && Boolean(onNewGroup);

  async function loadInbox() {
    try {
      setLoading(true);
      const [{ roles: nextRoles }, roomsRes] = await Promise.all([
        listRoles(),
        listRooms("group").catch(() => ({ rooms: [] as RoomSummary[] })),
      ]);
      setRoles(nextRoles);
      setRooms(roomsRes.rooms);
    } catch (err) {
      console.error("Failed to load inbox:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadInbox();
  }, [refreshKey]);

  useEffect(() => {
    if (!menu && !composeOpen) return;
    function closeMenu() {
      setMenu(null);
    }
    function closeCompose() {
      setComposeOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        closeMenu();
        closeCompose();
      }
    }
    function onPointerDown(e: globalThis.MouseEvent) {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (composeRef.current?.contains(target)) return;
      if (composeBtnRef.current?.contains(target)) return;
      closeMenu();
      closeCompose();
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("scroll", closeMenu, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("scroll", closeMenu, true);
    };
  }, [menu, composeOpen]);

  function placeMenu(e: ReactMouseEvent, height: number): { x: number; y: number } {
    const pad = 8;
    const approxW = 140;
    const x = Math.min(e.clientX, window.innerWidth - approxW - pad);
    const y = Math.min(e.clientY, window.innerHeight - height - pad);
    return { x: Math.max(pad, x), y: Math.max(pad, y) };
  }

  function openRoleMenu(e: ReactMouseEvent<HTMLButtonElement>, role: Role) {
    e.preventDefault();
    e.stopPropagation();
    setComposeOpen(false);
    setMenu({ kind: "role", role, ...placeMenu(e, 44) });
  }

  function openGroupMenu(e: ReactMouseEvent<HTMLButtonElement>, room: RoomSummary) {
    e.preventDefault();
    e.stopPropagation();
    setComposeOpen(false);
    setMenu({ kind: "group", room, ...placeMenu(e, 80) });
  }

  async function confirmDeleteRole(role: Role) {
    setMenu(null);
    if (role.is_default) {
      window.alert("不能删除默认角色");
      return;
    }
    if (
      !window.confirm(
        `确定删除角色「${role.name}」？\n其会话将一并删除，此操作不可撤销。`,
      )
    ) {
      return;
    }
    await onDeleteRole?.(role);
  }

  async function confirmDeleteGroup(room: RoomSummary) {
    setMenu(null);
    if (
      !window.confirm(
        `确定删除群「${room.title || "群聊"}」？此操作不可撤销。`,
      )
    ) {
      return;
    }
    await onDeleteGroup?.(room);
  }

  return (
    <aside className="role-list">
      <div className="role-list-toolbar">
        <button
          type="button"
          className="role-list-search-btn"
          onClick={() => setSearchOpen(true)}
          title={`搜索 ${workspaceSearchHotkeyLabel()}`}
          aria-label="搜索"
          aria-keyshortcuts="Control+K Meta+K"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
            <path
              d="M20 20l-3.5-3.5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <button
          ref={composeBtnRef}
          type="button"
          className="role-list-new-btn"
          onClick={() => {
            setMenu(null);
            setComposeOpen((open) => !open);
          }}
          title="新建角色或群聊"
          aria-label="新建"
          aria-expanded={composeOpen}
          aria-haspopup="menu"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      <div className="role-list-scroll">
        {loading && inbox.length === 0 ? (
          <div className="role-list-loading">加载中...</div>
        ) : inbox.length === 0 ? (
          <div className="role-list-empty">暂无对话</div>
        ) : (
          inbox.map((item) => {
            if (item.kind === "group") {
              const { room } = item;
              const active = activeGroupId === room.id;
              const title = room.title || "群聊";
              const preview = groupReplyPreview(room);
              const activityAt = room.last_active_at || room.updated_at;
              return (
                <button
                  key={`group:${room.id}`}
                  type="button"
                  className={`role-item${active ? " role-item--active" : ""}`}
                  onClick={() => onSelectGroup?.(room.id, room)}
                  onContextMenu={(e) => openGroupMenu(e, room)}
                >
                  <div className="role-item-avatar-wrap">
                    <GroupAvatar
                      name={title}
                      seed={room.id}
                      avatar={room.avatar}
                      members={room.participants}
                      size={36}
                    />
                  </div>
                  <div className="role-item-content">
                    <div className="role-item-top">
                      <div className="role-item-name">{title}</div>
                      <div className="role-item-meta">
                        {activityAt ? formatRoleListTime(activityAt) : ""}
                      </div>
                    </div>
                    <div className="role-item-preview">
                      {preview || "暂无对话"}
                    </div>
                  </div>
                </button>
              );
            }
            const { role } = item;
            const isActive = !activeGroupId && activeRoleId === role.id;
            const busy = busyRoleIds.includes(role.id);
            const preview = roleReplyPreview(role);
            const activityAt = role.last_active_at || role.updated_at;
            return (
              <button
                key={`role:${role.id}`}
                type="button"
                className={`role-item${isActive ? " role-item--active" : ""}`}
                onClick={() => onSelectRole(role.id)}
                onContextMenu={(e) => openRoleMenu(e, role)}
              >
                <div className="role-item-avatar-wrap">
                  <RoleAvatar
                    name={role.name}
                    seed={role.id}
                    avatar={role.avatar}
                    size={36}
                  />
                  {busy ? (
                    <span className="role-item-busy" title="忙碌中" />
                  ) : null}
                </div>
                <div className="role-item-content">
                  <div className="role-item-top">
                    <div className="role-item-name">{role.name}</div>
                    <div className="role-item-meta">
                      {formatRoleListTime(activityAt)}
                    </div>
                  </div>
                  <div className="role-item-preview">
                    {preview || "暂无对话"}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>

      <GlobalSearchPalette
        open={searchOpen}
        roles={roles}
        groups={rooms}
        onOpen={() => setSearchOpen(true)}
        onClose={() => setSearchOpen(false)}
        onSelectRole={onSelectRole}
        onSelectGroup={(id, room) => onSelectGroup?.(id, room)}
        onSearchHit={(hit) => onSearchHit?.(hit)}
        onSelectFile={onSelectFile}
      />

      {composeOpen &&
        createPortal(
          <ComposeMenu
            menuRef={composeRef}
            anchor={composeBtnRef.current}
            canCreateGroup={canCreateGroup}
            onNewRole={() => {
              setComposeOpen(false);
              onNewRole();
            }}
            onNewGroup={() => {
              setComposeOpen(false);
              onNewGroup?.();
            }}
          />,
          document.body,
        )}

      {menu &&
        createPortal(
          <div
            ref={menuRef}
            className="kb-tree-context-menu role-list-context-menu"
            style={{ left: menu.x, top: menu.y }}
            role="menu"
          >
            {menu.kind === "role" ? (
              menu.role.is_default ? (
                <button type="button" role="menuitem" disabled title="默认角色不可删除">
                  删除（不可用）
                </button>
              ) : (
                <button
                  type="button"
                  role="menuitem"
                  className="role-list-context-menu--danger"
                  onClick={() => void confirmDeleteRole(menu.role)}
                >
                  删除角色
                </button>
              )
            ) : (
              <>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    const room = menu.room;
                    setMenu(null);
                    onEditGroup?.(room);
                  }}
                >
                  群设置
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="role-list-context-menu--danger"
                  onClick={() => void confirmDeleteGroup(menu.room)}
                >
                  删除群聊
                </button>
              </>
            )}
          </div>,
          document.body,
        )}
    </aside>
  );
}

function ComposeMenu({
  menuRef,
  anchor,
  canCreateGroup,
  onNewRole,
  onNewGroup,
}: {
  menuRef: RefObject<HTMLDivElement | null>;
  anchor: HTMLButtonElement | null;
  canCreateGroup: boolean;
  onNewRole: () => void;
  onNewGroup: () => void;
}) {
  const rect = anchor?.getBoundingClientRect();
  const top = rect ? rect.bottom + 6 : 56;
  const left = rect ? Math.max(8, rect.right - 168) : 8;
  return (
    <div
      ref={menuRef}
      className="role-compose-menu"
      style={{ top, left }}
      role="menu"
    >
      <button type="button" role="menuitem" onClick={onNewRole}>
        <span className="role-compose-menu-icon" aria-hidden>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
            <path
              d="M5.5 19c.8-3.2 3.2-5 6.5-5s5.7 1.8 6.5 5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </span>
        新角色
      </button>
      <button
        type="button"
        role="menuitem"
        disabled={!canCreateGroup}
        title={canCreateGroup ? "圈选角色发起群聊" : "至少需要两个角色才能建群"}
        onClick={onNewGroup}
      >
        <span className="role-compose-menu-icon" aria-hidden>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="8.2" r="2.6" stroke="currentColor" strokeWidth="1.8" />
            <circle cx="16" cy="9" r="2.1" stroke="currentColor" strokeWidth="1.8" />
            <path
              d="M4 18.2c.5-2.3 2.3-3.6 4.8-3.6s4.3 1.3 4.8 3.6"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
            <path
              d="M13.6 17.6c.4-1.2 1.4-2 2.8-2 1.5 0 2.5.8 2.9 2.1"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </span>
        发起群聊
      </button>
    </div>
  );
}
