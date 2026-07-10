import { useEffect, useState } from "react";
import {
  getTree,
  listConversations,
  deleteConversation,
  type ConversationSummary,
} from "../api";
import { FileTree } from "./FileTree";

type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeConversationId: string | null;
  onSelectFile: (path: string) => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
};

function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString(undefined, { month: "numeric", day: "numeric" });
}

export function Sidebar({
  refreshKey = 0,
  selectedPath,
  activeConversationId,
  onSelectFile,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  async function refresh() {
    setDocs((await getTree()).docs as string[]);
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
    <aside className="sidebar">
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
          {conversations.map((c) => {
            const active = activeConversationId === c.id;
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
                  <span className="conversation-title">{c.title}</span>
                  <span className="conversation-meta">
                    {formatTime(c.updated_at)}
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
      </section>

      <section className="sidebar-section sidebar-tree-section">
        <div className="sidebar-section-head">
          <h4>知识库</h4>
          <button type="button" className="sidebar-refresh" onClick={refresh} title="刷新">
            ↻
          </button>
        </div>
        <FileTree
          paths={docs}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
        />
      </section>
    </aside>
  );
}
