import { useEffect, useMemo, useState } from "react";
import {
  getTree,
  listConversations,
  deleteConversation,
  type ConversationSummary,
} from "../api";
import { groupConversationsByTime } from "../utils/conversationGroups";
import { formatSidebarConversationTime } from "../utils/displayTime";
import { FileTree } from "./FileTree";
import { ThemeToggle } from "./ThemeToggle";

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeConversationId: string | null;
  /** 首问乐观标题；仅当服务端仍为「新对话」时覆盖展示 */
  titleOverrides?: Record<string, string>;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onOpenSettings?: () => void;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onDocsLoaded?: (paths: string[]) => void;
};

export function Sidebar({
  refreshKey = 0,
  selectedPath,
  activeConversationId,
  titleOverrides = {},
  collapsed = false,
  onToggleCollapsed,
  onOpenSettings,
  onSelectFile,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  onDocsLoaded,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const conversationGroups = useMemo(
    () => groupConversationsByTime(conversations),
    [conversations],
  );

  async function refresh() {
    const nextDocs = (await getTree()).docs as string[];
    setDocs(nextDocs);
    onDocsLoaded?.(nextDocs);
    setConversations((await listConversations()).conversations);
  }

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  async function handleDeleteConversation(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!window.confirm("确定删除这条对话记录？")) return;
    await deleteConversation(id);
    onDeleteConversation(id);
  }

  return (
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      {collapsed ? (
        <div className="sidebar-expand-rail">
          <button
            type="button"
            className="sidebar-expand-btn"
            title="展开侧栏"
            onClick={onToggleCollapsed}
          >
            »
          </button>
        </div>
      ) : (
        <>
          <section className="sidebar-section sidebar-chat-section">
            <div className="sidebar-section-head">
              <h4>对话</h4>
              <button type="button" className="sidebar-new-chat" onClick={onNewChat}>
                ＋ 新建
              </button>
            </div>
            <div className="conversation-list">
              {conversations.length === 0 && (
                <div className="conversation-empty">暂无历史对话</div>
              )}
              {conversationGroups.map((group) => (
                <div key={group.label} className="conversation-group">
                  <div className="conversation-group-label">{group.label}</div>
                  {group.items.map((c) => {
                    const active = activeConversationId === c.id;
                    const title =
                      c.title === "新对话" && titleOverrides[c.id]
                        ? titleOverrides[c.id]
                        : c.title;
                    return (
                      <div
                        key={c.id}
                        className={`conversation-item${active ? " active" : ""}`}
                      >
                        <button
                          type="button"
                          className="conversation-select"
                          onClick={() => onSelectConversation(c.id)}
                        >
                          <span className="conversation-title">{title}</span>
                          <span className="conversation-meta">
                            {formatSidebarConversationTime(c.updated_at)}
                            {c.message_count > 0 ? ` · ${c.message_count} 条` : ""}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="conversation-delete"
                          title="删除对话"
                          onClick={(e) => handleDeleteConversation(e, c.id)}
                        >
                          ×
                        </button>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </section>

          <section className="sidebar-section sidebar-tree-section">
            <div className="sidebar-section-head">
              <h4>知识库</h4>
              <div className="sidebar-section-actions">
                {onToggleCollapsed && (
                  <button
                    type="button"
                    className="sidebar-refresh"
                    title="收起侧栏"
                    onClick={onToggleCollapsed}
                  >
                    «
                  </button>
                )}
                <button type="button" className="sidebar-refresh" onClick={refresh} title="刷新">
                  ↻
                </button>
              </div>
            </div>
            <FileTree paths={docs} selectedPath={selectedPath} onSelectFile={onSelectFile} />
            <p className="sidebar-tree-hint">单击替换 · Ctrl+单击添加</p>
          </section>

          <footer className="sidebar-footer">
            <div className="sidebar-footer-actions">
              <ThemeToggle />
              {onOpenSettings ? (
                <button
                  type="button"
                  className="sidebar-settings-btn"
                  onClick={onOpenSettings}
                  title="系统设置"
                >
                  <span className="sidebar-settings-icon" aria-hidden>
                    ⚙
                  </span>
                  <span className="sidebar-settings-label">设置</span>
                </button>
              ) : null}
            </div>
          </footer>
        </>
      )}
    </aside>
  );
}
