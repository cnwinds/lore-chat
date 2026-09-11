import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  searchConversations,
  type ConversationSearchHit,
  type Role,
  type WorkspaceSearchScope,
} from "../../api";
import { formatSearchRelativeTime } from "../../utils/displayTime";
import { RoleAvatar } from "./RoleAvatar";

export type SearchTab = "all" | "messages" | "roles" | "files";

const TABS: { id: SearchTab; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "messages", label: "消息" },
  { id: "roles", label: "角色" },
  { id: "files", label: "文件" },
];

type Props = {
  open: boolean;
  roles: Role[];
  onClose: () => void;
  onSelectRole: (roleId: string) => void;
  onSearchHit: (hit: ConversationSearchHit) => void;
  onSelectFile?: (path: string) => void;
};

function badgeFor(kind: ConversationSearchHit["kind"]): string {
  if (kind === "role") return "角色";
  if (kind === "file") return "文件";
  return "消息";
}

function roleToHit(role: Role): ConversationSearchHit {
  return {
    kind: "role",
    conversation_id: "",
    message_id: null,
    role_id: role.id,
    role_name: role.name,
    role_avatar: role.avatar,
    title: role.name,
    snippet: role.last_reply_preview || role.system_prompt || "角色",
    ts: role.last_active_at || role.updated_at,
  };
}

export function GlobalSearchPalette({
  open,
  roles,
  onClose,
  onSelectRole,
  onSearchHit,
  onSelectFile,
}: Props) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<SearchTab>("all");
  const [hits, setHits] = useState<ConversationSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchGenRef = useRef(0);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setTab("all");
    setHits([]);
    setSearching(false);
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  const q = query.trim();
  const browseRoles = useMemo(() => {
    if (q) return [];
    if (tab !== "all" && tab !== "roles") return [];
    return roles.map(roleToHit);
  }, [q, tab, roles]);

  useEffect(() => {
    if (!open) return;
    if (!q) {
      setHits([]);
      setSearching(false);
      return;
    }
    const gen = ++searchGenRef.current;
    setSearching(true);
    const t = window.setTimeout(() => {
      void searchConversations({
        q,
        k: 16,
        scope: tab as WorkspaceSearchScope,
      })
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
  }, [open, q, tab]);

  if (!open) return null;

  const rows = q ? hits : browseRoles;
  const emptyHint = !q
    ? tab === "messages" || tab === "files"
      ? "输入关键词搜索"
      : roles.length === 0
        ? "暂无角色"
        : ""
    : searching
      ? "搜索中…"
      : "无匹配";

  function activate(hit: ConversationSearchHit) {
    const kind = hit.kind || "message";
    if (kind === "role" && hit.role_id) {
      onSelectRole(hit.role_id);
    } else if (kind === "file" && hit.path) {
      onSelectFile?.(hit.path);
    } else {
      onSearchHit(hit);
    }
    onClose();
  }

  return createPortal(
    <div
      className="workspace-search-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="workspace-search-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-search-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="workspace-search-input-row">
          <svg
            className="workspace-search-input-icon"
            width="16"
            height="16"
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
            ref={inputRef}
            id="workspace-search-title"
            type="search"
            className="workspace-search-input"
            placeholder="搜索"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="搜索角色、消息和文件"
          />
        </div>
        <div className="workspace-search-tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`workspace-search-tab${tab === item.id ? " is-active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="workspace-search-results">
          {rows.length === 0 ? (
            <div className="workspace-search-empty">{emptyHint}</div>
          ) : (
            rows.map((hit, index) => {
              const kind = hit.kind || "message";
              const name = hit.role_name || hit.title;
              const seed = hit.role_id || hit.path || hit.conversation_id || String(index);
              return (
                <button
                  key={`${kind}:${hit.conversation_id}:${hit.message_id || ""}:${hit.role_id || ""}:${hit.path || ""}:${index}`}
                  type="button"
                  className="workspace-search-hit"
                  onClick={() => activate(hit)}
                >
                  {kind === "file" ? (
                    <div className="workspace-search-file-icon" aria-hidden>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M7 3h7l5 5v13H7V3z"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                        <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.8" />
                      </svg>
                    </div>
                  ) : (
                    <RoleAvatar
                      name={name}
                      seed={seed}
                      avatar={hit.role_avatar}
                      size={32}
                    />
                  )}
                  <div className="workspace-search-hit-body">
                    <div className="workspace-search-hit-title">
                      {kind === "role" ? hit.title : hit.snippet || hit.title}
                    </div>
                    {kind !== "role" && hit.title && hit.snippet !== hit.title ? (
                      <div className="workspace-search-hit-sub">{hit.title}</div>
                    ) : null}
                  </div>
                  <div className="workspace-search-hit-meta">
                    {hit.ts ? (
                      <span className="workspace-search-hit-time">
                        {formatSearchRelativeTime(hit.ts)}
                      </span>
                    ) : null}
                    <span className="workspace-search-hit-badge">{badgeFor(kind)}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
