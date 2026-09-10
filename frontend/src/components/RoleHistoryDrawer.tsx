import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  deleteConversation,
  listConversations,
  type ConversationSummary,
  type RoleSummary,
} from "../api";
import { groupConversationsByTime } from "../utils/conversationGroups";
import { formatSidebarConversationTime } from "../utils/displayTime";

type Props = {
  open: boolean;
  role: RoleSummary | null;
  activeConversationId: string | null;
  titleOverrides?: Record<string, string>;
  onClose: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onShareConversation?: (id: string, title: string) => void;
};

export function RoleHistoryDrawer({
  open,
  role,
  activeConversationId,
  titleOverrides = {},
  onClose,
  onSelectConversation,
  onDeleteConversation,
  onShareConversation,
}: Props) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    if (!open || !role) {
      seqRef.current += 1;
      setConversations([]);
      setLoading(false);
      return;
    }
    const seq = ++seqRef.current;
    setConversations([]);
    setLoading(true);
    void listConversations({ roleId: role.id })
      .then((r) => {
        if (seq !== seqRef.current) return;
        setConversations(r.conversations);
      })
      .catch(() => {
        if (seq !== seqRef.current) return;
        setConversations([]);
      })
      .finally(() => {
        if (seq !== seqRef.current) return;
        setLoading(false);
      });
  }, [open, role]);

  const groups = useMemo(
    () => groupConversationsByTime(conversations),
    [conversations],
  );

  if (!open || !role) return null;

  return createPortal(
    <div className="role-history-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="role-history-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${role.name} 的历史`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="role-history-head">
          <h3>{role.name} · 历史</h3>
          <button type="button" className="role-settings-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="role-history-body">
          {loading && <div className="conversation-empty">加载中…</div>}
          {!loading && conversations.length === 0 && (
            <div className="conversation-empty">暂无历史对话</div>
          )}
          {!loading &&
            groups.map((group) => (
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
                        onClick={() => {
                          onSelectConversation(c.id);
                          onClose();
                        }}
                      >
                        <span className="conversation-title">{title}</span>
                        <span className="conversation-meta">
                          {formatSidebarConversationTime(c.updated_at)}
                          {c.message_count > 0
                            ? ` · ${c.message_count} 条`
                            : ""}
                        </span>
                      </button>
                      {onShareConversation && (
                        <button
                          type="button"
                          className="conversation-share"
                          title="分享对话"
                          onClick={(e) => {
                            e.stopPropagation();
                            onShareConversation(c.id, title);
                          }}
                        >
                          ↗
                        </button>
                      )}
                      <button
                        type="button"
                        className="conversation-delete"
                        title="删除"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!window.confirm("确定删除这条对话记录？")) return;
                          void deleteConversation(c.id).then(() => {
                            setConversations((prev) =>
                              prev.filter((x) => x.id !== c.id),
                            );
                            onDeleteConversation(c.id);
                          });
                        }}
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
