import { useEffect, useMemo, useRef, useState } from "react";
import {
  getTree,
  listConversations,
  deleteConversation,
  type ConversationSummary,
} from "../api";
import { groupConversationsByTime } from "../utils/conversationGroups";
import { formatSidebarConversationTime } from "../utils/displayTime";
import { FileTree } from "./FileTree";
import { KbFloatingRootDrop } from "./KbFloatingRootDrop";
import { KbTreeProgressBar } from "./KbTreeProgressBar";
import { ThemeToggle } from "./ThemeToggle";
import { useKbTreeActions } from "../hooks/useKbTreeActions";
import { useFileTreeInteraction } from "../hooks/useFileTreeInteraction";
import { useDragAutoScroll } from "../hooks/useDragAutoScroll";
import { useDismissOnOutsideClick } from "../hooks/useDismissOnOutsideClick";
import { useKbTreeViewportUi } from "../hooks/useKbTreeViewportUi";
import { isSystemLayerPath, SKILLS_DIR } from "../utils/fileTree";
import { SettingsAttentionDot } from "./settings/SettingsAttentionDot";

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean };

type Props = {
  refreshKey?: number;
  activePaths?: string[];
  activeConversationId: string | null;
  titleOverrides?: Record<string, string>;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onOpenSettings?: () => void;
  /** 设置内有待办（未配模型 / 待确认记忆 / 缺价目） */
  settingsAttention?: boolean;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onSelectFolder?: (path: string, mods?: SelectMods) => void;
  onOpenEnabledSkills?: () => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onKbPathChanged?: (fromPath: string, toPath: string) => void;
  onKbPathsDeleted?: (paths: string[]) => void;
  /** 知识库路径列表变更（供媒体图库等复用，避免重复 getTree） */
  onDocsChange?: (docs: string[]) => void;
};

export function Sidebar({
  refreshKey = 0,
  activePaths = [],
  activeConversationId,
  titleOverrides = {},
  collapsed = false,
  onToggleCollapsed,
  onOpenSettings,
  settingsAttention = false,
  onSelectFile,
  onSelectFolder,
  onOpenEnabledSkills,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  onKbPathChanged,
  onKbPathsDeleted,
  onDocsChange,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [kbHintOpen, setKbHintOpen] = useState(false);
  const kbHintRef = useRef<HTMLDivElement>(null);
  const treeScrollRef = useRef<HTMLDivElement>(null);
  const { onDragOverAutoScroll } = useDragAutoScroll(treeScrollRef);
  const viewport = useKbTreeViewportUi({
    paths: docs,
    activePaths,
    collapsed,
    scrollRef: treeScrollRef,
  });

  const conversationGroups = useMemo(
    () => groupConversationsByTime(conversations),
    [conversations],
  );

  async function refresh() {
    const nextDocs = (await getTree()).docs as string[];
    setDocs(nextDocs);
    onDocsChange?.(nextDocs);
    setConversations((await listConversations()).conversations);
  }

  const kb = useKbTreeActions(refresh, docs);
  const tree = useFileTreeInteraction({
    kb,
    onKbPathChanged,
    onKbPathsDeleted,
  });

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  useDismissOnOutsideClick(tree.menuRef, !!tree.menu, tree.closeMenu);
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

  return (
    <aside className={`sidebar${collapsed ? " sidebar--collapsed" : ""}`}>
      {kb.conflictDialog}
      {tree.menu && (
        <div
          ref={tree.menuRef}
          className="kb-tree-context-menu"
          style={{ left: tree.menu.x, top: tree.menu.y }}
          role="menu"
        >
          {(tree.menu.ctx.kind === "file" ||
            (tree.menu.ctx.kind === "folder" && !isSystemLayerPath(tree.menu.ctx.path))) && (
            <button type="button" role="menuitem" onClick={() => void tree.handleMenuAction("download")}>
              下载
            </button>
          )}
          {tree.menu.ctx.kind === "folder" &&
            tree.menu.ctx.path === SKILLS_DIR &&
            onOpenEnabledSkills && (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onOpenEnabledSkills();
                  tree.closeMenu();
                }}
              >
                启用 Skill…
              </button>
            )}
          {!isSystemLayerPath(tree.menu.ctx.path) && (
            <button type="button" role="menuitem" onClick={() => void tree.handleMenuAction("rename")}>
              重命名
            </button>
          )}
          {!isSystemLayerPath(tree.menu.ctx.path) && (
            <button type="button" role="menuitem" onClick={() => void tree.handleMenuAction("delete")}>
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
            className="sidebar-section sidebar-tree-section"
            onDragEnter={tree.onKbSectionDragEnter}
            onDragLeave={tree.onKbSectionDragLeave}
            onDragOver={tree.onRootDragOver}
            onDrop={tree.onRootDrop}
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
                        <strong>单击</strong> Markdown 打开预览；图片用灯箱；附件下载
                      </li>
                      <li>
                        <strong>单击媒体末级目录</strong>（如「媒体/生成/2026-08」）以浮窗打开图片瓦片图库；媒体树下不列出文件
                      </li>
                      <li>
                        <strong>Ctrl / ⌘ + 单击</strong>{" "}
                        文件或目录加入工作托盘（顶层「技能」除外；标明本轮主要工作对象）
                      </li>
                      <li>
                        <strong>双击</strong> 文件名重命名；文件夹可右键重命名
                      </li>
                      <li>
                        <strong>Ctrl+单击顶层「技能」</strong>{" "}
                        （或右键「启用 Skill…」）维护默认启用的 Skill（跨会话；与托盘无关）
                      </li>
                      <li>
                        <strong>拖入</strong> 到文件夹行；移动或上传时顶部会出现「根目录」
                      </li>
                      <li>
                        <strong>拖拽</strong> 文件或文件夹到其他目录可移动
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
            {kb.treeProgress ? (
              <KbTreeProgressBar progress={kb.treeProgress} />
            ) : null}
            <div
              className="sidebar-tree-body"
              onDragOverCapture={onDragOverAutoScroll}
            >
              <div ref={treeScrollRef} className="sidebar-tree-scroll">
                <FileTree
                  tree={viewport.tree}
                  activePaths={activePaths}
                  onSelectFile={onSelectFile}
                  onSelectFolder={onSelectFolder}
                  expanded={viewport.expanded}
                  onToggleFolder={viewport.toggleFolder}
                  {...tree.fileTreeProps}
                />
              </div>
              <KbFloatingRootDrop
                visible={tree.showFloatingRoot}
                active={tree.floatingRootActive}
                uploadMode={tree.floatingRootUploadMode}
                onDragOver={tree.onFloatingRootDragOver}
                onDrop={tree.onFloatingRootDrop}
              />
            </div>
          </section>

          <footer className="sidebar-footer">
            <div className="sidebar-footer-actions">
              <ThemeToggle />
              {onOpenSettings ? (
                <button
                  type="button"
                  className="sidebar-settings-btn"
                  onClick={onOpenSettings}
                  title={
                    settingsAttention
                      ? "系统设置（有待办）"
                      : "系统设置"
                  }
                >
                  <span className="sidebar-settings-icon" aria-hidden>
                    ⚙
                  </span>
                  <span className="sidebar-settings-label">
                    设置
                    {settingsAttention ? (
                      <SettingsAttentionDot title="有待办" />
                    ) : null}
                  </span>
                </button>
              ) : null}
            </div>
          </footer>
        </>
      )}
    </aside>
  );
}
