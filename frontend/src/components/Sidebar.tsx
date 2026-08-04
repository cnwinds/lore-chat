import { useEffect, useMemo, useRef, useState } from "react";
import {
  downloadUrl,
  getTree,
  listConversations,
  deleteConversation,
  type ConversationSummary,
} from "../api";
import { groupConversationsByTime } from "../utils/conversationGroups";
import { formatSidebarConversationTime } from "../utils/displayTime";
import { FileTree, type FileTreeNodeContext } from "./FileTree";
import { ThemeToggle } from "./ThemeToggle";
import { useKbTreeActions } from "../hooks/useKbTreeActions";
import { useDismissOnOutsideClick } from "../hooks/useDismissOnOutsideClick";
import { isSystemLayerPath } from "../utils/fileTree";

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

type Props = {
  refreshKey?: number;
  selectedPath: string | null;
  activeConversationId: string | null;
  titleOverrides?: Record<string, string>;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onOpenSettings?: () => void;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onDocsLoaded?: (paths: string[]) => void;
  onKbPathChanged?: (fromPath: string, toPath: string) => void;
  onKbPathsDeleted?: (paths: string[]) => void;
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
  onKbPathChanged,
  onKbPathsDeleted,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [dropHighlightDir, setDropHighlightDir] = useState<string | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renamingValue, setRenamingValue] = useState("");
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    ctx: FileTreeNodeContext;
  } | null>(null);
  const [kbHintOpen, setKbHintOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const kbHintRef = useRef<HTMLDivElement>(null);

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

  const kb = useKbTreeActions(refresh);

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  useDismissOnOutsideClick(menuRef, !!menu, () => setMenu(null));
  useDismissOnOutsideClick(
    kbHintRef,
    kbHintOpen,
    () => setKbHintOpen(false),
    { escape: true },
  );

  async function handleDeleteConversation(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!window.confirm("确定删除这条对话记录？")) return;
    await deleteConversation(id);
    onDeleteConversation(id);
  }

  function startRename(path: string, name: string) {
    if (isSystemLayerPath(path)) return;
    setRenamingPath(path);
    setRenamingValue(name);
  }

  async function commitRename() {
    if (!renamingPath) return;
    const trimmed = renamingValue.trim();
    setRenamingPath(null);
    if (!trimmed || trimmed === renamingPath.split("/").pop()) return;
    const newPath = await kb.renameFile(renamingPath, trimmed);
    if (newPath && newPath !== renamingPath) {
      onKbPathChanged?.(renamingPath, newPath);
    }
  }

  function openContextMenu(e: React.MouseEvent, ctx: FileTreeNodeContext) {
    if (isSystemLayerPath(ctx.path) && ctx.kind === "folder") return;
    setMenu({ x: e.clientX, y: e.clientY, ctx });
  }

  async function handleMenuAction(action: string) {
    if (!menu) return;
    const { ctx } = menu;
    setMenu(null);
    const path = ctx.path;

    if (action === "download" && ctx.kind === "file") {
      window.open(downloadUrl(path), "_blank", "noopener,noreferrer");
      return;
    }
    if (action === "rename" && ctx.kind === "file") {
      startRename(path, ctx.node.type === "file" ? ctx.node.name : path);
      return;
    }
    if (action === "delete") {
      const label =
        ctx.kind === "folder"
          ? `确定删除文件夹「${path || "根目录"}」及其下全部文件？`
          : `确定删除「${path}」？`;
      if (!window.confirm(label)) return;
      const deleted = await kb.deletePath(path);
      onKbPathsDeleted?.(deleted);
      return;
    }
  }

  async function handleDropFiles(files: FileList, directory: string) {
    if (isSystemLayerPath(directory)) return;
    await kb.importMany(files, directory);
  }

  async function handleMovePath(fromPath: string, toDirectory: string) {
    if (isSystemLayerPath(fromPath) || isSystemLayerPath(toDirectory)) return;
    const base = fromPath.split("/").pop();
    if (!base) return;
    const newPath = await kb.moveFile(fromPath, toDirectory, base);
    if (newPath && newPath !== fromPath) {
      onKbPathChanged?.(fromPath, newPath);
    }
  }

  function handleSectionDrop(e: React.DragEvent) {
    e.preventDefault();
    setDropHighlightDir(null);
    if (kb.busy) return;
    if (e.dataTransfer.files?.length) {
      void handleDropFiles(e.dataTransfer.files, "");
    }
  }

  return (
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      {kb.conflictDialog}
      {menu && (
        <div
          ref={menuRef}
          className="kb-tree-context-menu"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
        >
          {menu.ctx.kind === "file" && (
            <>
              <button type="button" role="menuitem" onClick={() => void handleMenuAction("download")}>
                下载
              </button>
              {!isSystemLayerPath(menu.ctx.path) && (
                <button type="button" role="menuitem" onClick={() => void handleMenuAction("rename")}>
                  重命名
                </button>
              )}
            </>
          )}
          {!isSystemLayerPath(menu.ctx.path) && (
            <button type="button" role="menuitem" onClick={() => void handleMenuAction("delete")}>
              删除
            </button>
          )}
        </div>
      )}
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

          <section
            className={`sidebar-section sidebar-tree-section${dropHighlightDir === "" ? " drop-target-root" : ""}`}
            onDragOver={(e) => {
              if (kb.busy) return;
              e.preventDefault();
              setDropHighlightDir("");
            }}
            onDragLeave={() => setDropHighlightDir(null)}
            onDrop={handleSectionDrop}
          >
            <div className="sidebar-section-head">
              <div className="sidebar-section-title" ref={kbHintRef}>
                <h4>知识库</h4>
                <button
                  type="button"
                  className={`sidebar-hint-btn${kbHintOpen ? " open" : ""}`}
                  aria-label="知识库使用说明"
                  aria-expanded={kbHintOpen}
                  onClick={(e) => {
                    e.stopPropagation();
                    setKbHintOpen((v) => !v);
                  }}
                >
                  ?
                </button>
                {kbHintOpen && (
                  <div className="sidebar-kb-hint-popover" role="dialog" aria-label="知识库使用说明">
                    <p className="sidebar-kb-hint-lead">文档与附件</p>
                    <ul className="sidebar-kb-hint-list">
                      <li>
                        <strong>单击</strong> Markdown 打开预览；附件触发下载
                      </li>
                      <li>
                        <strong>Ctrl / ⌘ + 单击</strong> 加入对话文档托盘
                      </li>
                      <li>
                        <strong>双击</strong> 文件名重命名
                      </li>
                      <li>
                        <strong>右键</strong> 下载、重命名、删除
                      </li>
                      <li>
                        <strong>拖入</strong> 本地文件到文件夹（空白区域为根目录）
                      </li>
                      <li>
                        <strong>拖拽</strong> 文件到另一文件夹可移动
                      </li>
                    </ul>
                  </div>
                )}
              </div>
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
            <FileTree
              paths={docs}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              dropHighlightDir={dropHighlightDir}
              onDropHighlightDir={setDropHighlightDir}
              onDropFiles={handleDropFiles}
              onMovePath={handleMovePath}
              onContextMenu={openContextMenu}
              renamingPath={renamingPath}
              renamingValue={renamingValue}
              onRenamingValueChange={setRenamingValue}
              onRenameCommit={() => void commitRename()}
              onRenameCancel={() => setRenamingPath(null)}
              onStartRename={startRename}
              disabled={kb.busy}
            />
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
