import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  listRoles,
  type ConversationSearchHit,
  type Role,
} from "../../api";
import { formatRoleListTime } from "../../utils/displayTime";
import {
  roleReplyPreview,
  sortRolesByRecentActivity,
} from "../../utils/roleListPreview";
import { workspaceSearchHotkeyLabel } from "../../utils/workspaceSearch";
import { GlobalSearchPalette } from "./GlobalSearchPalette";
import { RoleAvatar } from "./RoleAvatar";

type RoleMenu = {
  role: Role;
  x: number;
  y: number;
};

type Props = {
  activeRoleId: string | null;
  onSelectRole: (roleId: string) => void;
  onNewRole: () => void;
  onDeleteRole?: (role: Role) => void | Promise<void>;
  onSearchHit?: (hit: ConversationSearchHit) => void;
  onSelectFile?: (path: string) => void;
  busyRoleIds?: string[];
  refreshKey?: number;
};

export function RoleList({
  activeRoleId,
  onSelectRole,
  onNewRole,
  onDeleteRole,
  onSearchHit,
  onSelectFile,
  busyRoleIds = [],
  refreshKey = 0,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [menu, setMenu] = useState<RoleMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const orderedRoles = useMemo(
    () => sortRolesByRecentActivity(roles, busyRoleIds),
    [roles, busyRoleIds],
  );

  async function loadRoles() {
    try {
      setLoading(true);
      const { roles: data } = await listRoles();
      setRoles(data);
    } catch (err) {
      console.error("Failed to load roles:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRoles();
  }, [refreshKey]);

  useEffect(() => {
    if (!menu) return;
    function close() {
      setMenu(null);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    function onPointerDown(e: globalThis.MouseEvent) {
      if (menuRef.current?.contains(e.target as Node)) return;
      close();
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  function openMenu(e: ReactMouseEvent<HTMLButtonElement>, role: Role) {
    e.preventDefault();
    e.stopPropagation();
    const pad = 8;
    const approxW = 140;
    const approxH = 44;
    const x = Math.min(e.clientX, window.innerWidth - approxW - pad);
    const y = Math.min(e.clientY, window.innerHeight - approxH - pad);
    setMenu({ role, x: Math.max(pad, x), y: Math.max(pad, y) });
  }

  async function confirmDelete(role: Role) {
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
          type="button"
          className="role-list-new-btn"
          onClick={onNewRole}
          title="新建角色"
          aria-label="新建角色"
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
        {loading && roles.length === 0 ? (
          <div className="role-list-loading">加载中...</div>
        ) : roles.length === 0 ? (
          <div className="role-list-empty">暂无角色</div>
        ) : (
          orderedRoles.map((role) => {
            const isActive = activeRoleId === role.id;
            const busy = busyRoleIds.includes(role.id);
            const preview = roleReplyPreview(role);
            const activityAt = role.last_active_at || role.updated_at;
            return (
              <button
                key={role.id}
                type="button"
                className={`role-item${isActive ? " role-item--active" : ""}`}
                onClick={() => onSelectRole(role.id)}
                onContextMenu={(e) => openMenu(e, role)}
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
        onOpen={() => setSearchOpen(true)}
        onClose={() => setSearchOpen(false)}
        onSelectRole={onSelectRole}
        onSearchHit={(hit) => onSearchHit?.(hit)}
        onSelectFile={onSelectFile}
      />

      {menu &&
        createPortal(
          <div
            ref={menuRef}
            className="kb-tree-context-menu role-list-context-menu"
            style={{ left: menu.x, top: menu.y }}
            role="menu"
          >
            {menu.role.is_default ? (
              <button type="button" role="menuitem" disabled title="默认角色不可删除">
                删除（不可用）
              </button>
            ) : (
              <button
                type="button"
                role="menuitem"
                className="role-list-context-menu--danger"
                onClick={() => void confirmDelete(menu.role)}
              >
                删除角色
              </button>
            )}
          </div>,
          document.body,
        )}
    </aside>
  );
}
