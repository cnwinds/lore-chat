import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  listRoles,
  searchConversations,
  type ConversationSearchHit,
  type Role,
} from "../../api";
import { formatRoleListTime } from "../../utils/displayTime";
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
  busyRoleIds?: string[];
  refreshKey?: number;
};

export function RoleList({
  activeRoleId,
  onSelectRole,
  onNewRole,
  onDeleteRole,
  onSearchHit,
  busyRoleIds = [],
  refreshKey = 0,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ConversationSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [menu, setMenu] = useState<RoleMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchGenRef = useRef(0);

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
    const q = query.trim();
    if (!q || !activeRoleId) {
      setHits([]);
      setSearching(false);
      return;
    }
    const gen = ++searchGenRef.current;
    setSearching(true);
    const t = window.setTimeout(() => {
      void searchConversations({ q, roleId: activeRoleId, k: 12 })
        .then((res) => {
          if (gen !== searchGenRef.current) return;
          setHits(res.hits);
        })
        .catch(() => {
          if (gen !== searchGenRef.current) return;
          setHits([]);
        })
        .finally(() => {
          if (gen === searchGenRef.current) setSearching(false);
        });
    }, 220);
    return () => window.clearTimeout(t);
  }, [query, activeRoleId]);

  useEffect(() => {
    if (!menu) return;
    function close() {
      setMenu(null);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    function onPointerDown(e: MouseEvent) {
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

  function openMenu(e: React.MouseEvent, role: Role) {
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
        `确定删除角色「${role.name}」？\n其会话将迁回默认角色，此操作不可撤销。`,
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
      <div className="role-list-search">
        <svg
          className="role-list-search-icon"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path
            d="M20 20l-3.5-3.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        <input
          type="search"
          className="role-list-search-input"
          placeholder="搜索"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={!activeRoleId}
          aria-label="搜索本角色会话"
        />
      </div>

      {query.trim() && (
        <div className="role-list-search-results">
          {searching && hits.length === 0 ? (
            <div className="role-list-loading">搜索中…</div>
          ) : hits.length === 0 ? (
            <div className="role-list-empty">无匹配</div>
          ) : (
            hits.map((hit) => (
              <button
                key={`${hit.conversation_id}:${hit.message_id || ""}:${hit.ts || ""}`}
                type="button"
                className="role-search-hit"
                onClick={() => {
                  onSearchHit?.(hit);
                  setQuery("");
                  setHits([]);
                }}
              >
                <div className="role-search-hit-title">{hit.title}</div>
                <div className="role-search-hit-snippet">{hit.snippet}</div>
              </button>
            ))
          )}
        </div>
      )}

      <div className="role-list-scroll">
        {loading && roles.length === 0 ? (
          <div className="role-list-loading">加载中...</div>
        ) : roles.length === 0 ? (
          <div className="role-list-empty">暂无角色</div>
        ) : (
          roles.map((role) => {
            const isActive = activeRoleId === role.id;
            const busy = busyRoleIds.includes(role.id);
            const preview = (role.system_prompt || "").replace(/\s+/g, " ").trim();
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
                  <div className="role-item-name">{role.name}</div>
                  <div className="role-item-preview">
                    {preview || "暂无人设"}
                  </div>
                </div>
                <div className="role-item-meta">
                  {formatRoleListTime(role.updated_at)}
                </div>
              </button>
            );
          })
        )}
      </div>

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
