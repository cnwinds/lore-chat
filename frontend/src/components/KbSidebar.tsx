import { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { getTree } from "../api";
import { scrollKbTreeNodeIntoView } from "../utils/kbTreeScroll";
import { FileTree } from "./FileTree";
import { KbFloatingRootDrop } from "./KbFloatingRootDrop";
import { KbTreeProgressBar } from "./KbTreeProgressBar";
import { useKbTreeActions } from "../hooks/useKbTreeActions";
import { useFileTreeInteraction } from "../hooks/useFileTreeInteraction";
import { useDragAutoScroll } from "../hooks/useDragAutoScroll";
import { useDismissOnOutsideClick } from "../hooks/useDismissOnOutsideClick";
import { useKbTreeViewportUi } from "../hooks/useKbTreeViewportUi";
import { isProtectedKbPath, SKILLS_DIR } from "../utils/fileTree";

/** 与 portal style / CSS 共用：知识库 tip 最大高度上限（px） */
const KB_HINT_POPOVER_MAX_PX = 420;

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean };

type Props = {
  refreshKey?: number;
  activePaths?: string[];
  memoryAttention?: boolean;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onSelectFolder?: (path: string, mods?: SelectMods) => void;
  onOpenEnabledSkills?: () => void;
  onKbPathChanged?: (fromPath: string, toPath: string) => void;
  onKbPathsDeleted?: (paths: string[]) => void;
  onDocsChange?: (docs: string[]) => void;
  onBindLocateKbPath?: (locate: ((path: string) => void) | null) => void;
};

export function KbSidebar({
  refreshKey = 0,
  activePaths = [],
  memoryAttention = false,
  onSelectFile,
  onSelectFolder,
  onOpenEnabledSkills,
  onKbPathChanged,
  onKbPathsDeleted,
  onDocsChange,
  onBindLocateKbPath,
}: Props) {
  const [docs, setDocs] = useState<string[]>([]);
  const [kbHintOpen, setKbHintOpen] = useState(false);
  const [kbHintPos, setKbHintPos] = useState<{ top: number; left: number } | null>(null);
  const kbHintRef = useRef<HTMLDivElement>(null);
  const kbHintPopoverRef = useRef<HTMLDivElement>(null);
  const treeScrollRef = useRef<HTMLDivElement>(null);
  const { onDragOverAutoScroll } = useDragAutoScroll(treeScrollRef);
  const viewport = useKbTreeViewportUi({
    paths: docs,
    activePaths,
    collapsed: false,
    scrollRef: treeScrollRef,
  });

  async function refresh() {
    const nextDocs = (await getTree()).docs as string[];
    setDocs(nextDocs);
    onDocsChange?.(nextDocs);
  }

  const kb = useKbTreeActions(refresh, docs);
  const treeInteraction = useFileTreeInteraction({
    kb,
    onKbPathChanged,
    onKbPathsDeleted,
  });

  const { tree: kbTree, expanded, toggleFolder, revealPath } = viewport;

  const locateKbPath = useCallback(
    (path: string) => {
      revealPath(path);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const scrollRoot = treeScrollRef.current;
          if (!scrollRoot) return;
          const escaped = CSS.escape(path);
          const el = scrollRoot.querySelector(`[data-kb-path="${escaped}"]`);
          if (el instanceof HTMLElement) {
            scrollKbTreeNodeIntoView(el);
          }
        });
      });
    },
    [revealPath],
  );

  useEffect(() => {
    onBindLocateKbPath?.(locateKbPath);
    return () => onBindLocateKbPath?.(null);
  }, [locateKbPath, onBindLocateKbPath]);

  useEffect(() => {
    void refresh();
  }, [refreshKey]);

  useLayoutEffect(() => {
    if (!kbHintOpen) {
      setKbHintPos(null);
      return;
    }
    function updateKbHintPopoverPosition() {
      const anchor = kbHintRef.current;
      if (!anchor) return;
      const r = anchor.getBoundingClientRect();
      const width = Math.min(280, window.innerWidth - 24);
      let left = r.left;
      if (left + width > window.innerWidth - 12) {
        left = window.innerWidth - 12 - width;
      }
      left = Math.max(12, left);
      const fallbackH = Math.min(window.innerHeight * 0.85, KB_HINT_POPOVER_MAX_PX);
      const popH = kbHintPopoverRef.current?.offsetHeight ?? fallbackH;
      let top = r.bottom + 8;
      if (top + popH > window.innerHeight - 12) {
        top = Math.max(12, r.top - 8 - popH);
      }
      setKbHintPos((prev) =>
        prev && prev.top === top && prev.left === left ? prev : { top, left },
      );
    }
    updateKbHintPopoverPosition();
    const raf = window.requestAnimationFrame(updateKbHintPopoverPosition);
    window.addEventListener("resize", updateKbHintPopoverPosition);
    window.addEventListener("scroll", updateKbHintPopoverPosition, true);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", updateKbHintPopoverPosition);
      window.removeEventListener("scroll", updateKbHintPopoverPosition, true);
    };
  }, [kbHintOpen]);

  useDismissOnOutsideClick(treeInteraction.menuRef, !!treeInteraction.menu, treeInteraction.closeMenu);
  useDismissOnOutsideClick(
    [kbHintRef, kbHintPopoverRef],
    kbHintOpen,
    () => setKbHintOpen(false),
    { escape: true },
  );

  return (
    <div className="kb-sidebar">
      {kb.conflictDialog}
      {treeInteraction.menu && (
        <div
          ref={treeInteraction.menuRef}
          className="kb-tree-context-menu"
          style={{ left: treeInteraction.menu.x, top: treeInteraction.menu.y }}
          role="menu"
        >
          {(treeInteraction.menu.ctx.kind === "file" ||
            (treeInteraction.menu.ctx.kind === "folder" &&
              !isProtectedKbPath(treeInteraction.menu.ctx.path))) && (
            <button type="button" role="menuitem" onClick={() => void treeInteraction.handleMenuAction("download")}>
              下载
            </button>
          )}
          {treeInteraction.menu.ctx.kind === "folder" &&
            treeInteraction.menu.ctx.path === SKILLS_DIR &&
            onOpenEnabledSkills && (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  onOpenEnabledSkills();
                  treeInteraction.closeMenu();
                }}
              >
                启用 Skill…
              </button>
            )}
          {!isProtectedKbPath(treeInteraction.menu.ctx.path) && (
            <button type="button" role="menuitem" onClick={() => void treeInteraction.handleMenuAction("rename")}>
              重命名
            </button>
          )}
          {!isProtectedKbPath(treeInteraction.menu.ctx.path) && (
            <button type="button" role="menuitem" onClick={() => void treeInteraction.handleMenuAction("delete")}>
              删除
            </button>
          )}
        </div>
      )}

      <section
        className="kb-sidebar-section"
        onDragEnter={treeInteraction.onKbSectionDragEnter}
        onDragLeave={treeInteraction.onKbSectionDragLeave}
        onDragOver={treeInteraction.onRootDragOver}
        onDrop={treeInteraction.onRootDrop}
      >
        <div className="kb-sidebar-head">
          <div className="kb-sidebar-title" ref={kbHintRef}>
            <h4>知识库</h4>
            <button
              type="button"
              className={`kb-hint-btn${kbHintOpen ? " open" : ""}`}
              aria-label="知识库使用说明"
              aria-expanded={kbHintOpen}
              onClick={(e) => {
                e.stopPropagation();
                setKbHintOpen((v) => !v);
              }}
            >
              ?
            </button>
            {kbHintOpen &&
              kbHintPos &&
              createPortal(
                <div
                  ref={kbHintPopoverRef}
                  className="kb-hint-popover"
                  role="dialog"
                  aria-label="知识库使用说明"
                  style={{
                    top: kbHintPos.top,
                    left: kbHintPos.left,
                    maxHeight: `min(85vh, ${KB_HINT_POPOVER_MAX_PX}px)`,
                  }}
                >
                  <p className="kb-hint-lead">文档与附件</p>
                  <ul className="kb-hint-list">
                    <li>
                      <strong>单击</strong> Markdown 打开预览；图片用灯箱；附件下载
                    </li>
                    <li>
                      <strong>单击「记忆」</strong>{" "}
                      以浮窗打开长期画像（确认 / 拒绝 / 编辑 / 遗忘）；数据在数据库，不落盘
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
                </div>,
                document.body,
              )}
          </div>
          <div className="kb-sidebar-actions">
            <button type="button" className="kb-refresh-btn" onClick={refresh} title="刷新">
              ↻
            </button>
          </div>
        </div>
        {kb.treeProgress ? <KbTreeProgressBar progress={kb.treeProgress} /> : null}
        <div className="kb-sidebar-body" onDragOverCapture={onDragOverAutoScroll}>
          <div ref={treeScrollRef} className="kb-sidebar-scroll">
            <FileTree
              tree={kbTree}
              activePaths={activePaths}
              onSelectFile={onSelectFile}
              onSelectFolder={onSelectFolder}
              expanded={expanded}
              onToggleFolder={toggleFolder}
              memoryAttention={memoryAttention}
              {...treeInteraction.fileTreeProps}
            />
          </div>
          <KbFloatingRootDrop
            visible={treeInteraction.showFloatingRoot}
            active={treeInteraction.floatingRootActive}
            uploadMode={treeInteraction.floatingRootUploadMode}
            onDragOver={treeInteraction.onFloatingRootDragOver}
            onDrop={treeInteraction.onFloatingRootDrop}
          />
        </div>
      </section>
    </div>
  );
}
