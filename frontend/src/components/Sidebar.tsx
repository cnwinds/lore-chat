import { useEffect, useState } from "react";
import {
  getTree,
  listConversations,
  deleteConversation,
  type MergeResult,
  type ConversationSummary,
} from "../api";
import { FileTree } from "./FileTree";
import { MergeConfigModal } from "./MergeConfigModal";
import { ThemeToggle } from "./ThemeToggle";

type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeConversationId: string | null;
  /** 首问乐观标题；仅当服务端仍为「新对话」时覆盖展示 */
  titleOverrides?: Record<string, string>;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onSelectFile: (path: string) => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  selectionMode?: boolean;
  selectedPaths?: Set<string>;
  onToggleSelectionMode?: () => void;
  onToggleSelect?: (path: string, shiftKey?: boolean) => void;
  onSelectFolderAll?: (paths: string[]) => void;
  onMergeComplete?: (result: MergeResult) => void;
  onDocsLoaded?: (paths: string[]) => void;
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
  titleOverrides = {},
  collapsed = false,
  onToggleCollapsed,
  onSelectFile,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  selectionMode = false,
  selectedPaths = new Set(),
  onToggleSelectionMode,
  onToggleSelect,
  onSelectFolderAll,
  onMergeComplete,
  onDocsLoaded,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [showMergeModal, setShowMergeModal] = useState(false);

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
              {conversations.map((c) => {
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
                <button
                  type="button"
                  className={`sidebar-multi-select-toggle${selectionMode ? " is-active" : ""}`}
                  onClick={onToggleSelectionMode}
                  title="多选模式"
                >
                  多选
                </button>
              </div>
            </div>
            <FileTree
              paths={docs}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              selectionMode={selectionMode}
              selectedPaths={selectedPaths}
              onToggleSelect={onToggleSelect}
              onPreviewFile={onSelectFile}
              onSelectFolderAll={onSelectFolderAll}
            />
            {selectionMode && selectedPaths.size >= 1 && (
              <div className="sidebar-selection-bar">
                <span>已选 {selectedPaths.size} 篇</span>
                <button
                  type="button"
                  className="sidebar-merge-btn"
                  disabled={selectedPaths.size < 2}
                  onClick={() => setShowMergeModal(true)}
                >
                  合并为文档
                </button>
              </div>
            )}
          </section>

          <footer className="sidebar-footer">
            <ThemeToggle />
          </footer>
          {showMergeModal && (
            <MergeConfigModal
              paths={[...selectedPaths]}
              onClose={() => setShowMergeModal(false)}
              onSubmit={(result) => {
                setShowMergeModal(false);
                onMergeComplete?.(result);
              }}
            />
          )}
        </>
      )}
    </aside>
  );
}
