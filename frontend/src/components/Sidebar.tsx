import { useEffect, useState } from "react";
import {
  getTree,
  getQuestions,
  resolveQuestion,
  listConversations,
  deleteConversation,
  type Question,
  type ConversationSummary,
} from "../api";
import { FileTree } from "./FileTree";

type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeView: "chat" | "doc";
  activeConversationId: string | null;
  onSelectFile: (path: string) => void;
  onOpenChat: () => void;
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
  activeView,
  activeConversationId,
  onSelectFile,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  async function refresh() {
    setDocs((await getTree()).docs as string[]);
    setQuestions((await getQuestions()).questions);
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
            const active =
              activeView === "chat" && activeConversationId === c.id;
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

      {questions.length > 0 && (
        <section className="sidebar-section">
          <h4>待我确认</h4>
          {questions.map((q) => (
            <div key={q.id} className="pending-item">
              <div>{q.question}</div>
              {q.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className="pending-btn"
                  onClick={async () => {
                    await resolveQuestion(q.id, o.id);
                    refresh();
                  }}
                >
                  {o.label}
                </button>
              ))}
            </div>
          ))}
        </section>
      )}

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
