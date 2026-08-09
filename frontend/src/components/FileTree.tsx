import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import {
  buildFileTree,
  collectAncestorFolderPaths,
  isSystemLayerPath,
  nextUserExpandedAfterTreeChange,
  resolveExpandedFolderPaths,
  type TreeNode,
} from "../utils/fileTree";
import { isMarkdownPath } from "../api";
import { dropEffectForTransfer } from "../utils/droppedFiles";
import {
  hasPersistedExpanded,
  loadKbTreeUi,
  saveKbTreeExpanded,
  saveKbTreeExpandedIfPersisted,
} from "../utils/kbTreeUiStorage";

function parentDirectoryFromPath(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx);
}

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

export type FileTreeNodeContext = {
  node: TreeNode;
  kind: "file" | "folder";
  path: string;
};

type Props = {
  paths: string[];
  /** 当前在预览中打开的文件路径（侧边栏高亮） */
  activePaths?: string[];
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onSelectFolder?: (path: string, mods?: SelectMods) => void;
  dropHighlightDir: string | null;
  onDropHighlightDir: (dir: string | null) => void;
  onDropFiles: (dataTransfer: DataTransfer, directory: string) => void;
  onMovePath: (fromPath: string, toDirectory: string) => void;
  onInternalDragStart?: () => void;
  onInternalDragEnd?: () => void;
  onContextMenu: (e: React.MouseEvent, ctx: FileTreeNodeContext) => void;
  renamingPath: string | null;
  renamingValue: string;
  onRenamingValueChange: (v: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onStartRename: (path: string, currentName: string) => void;
  disabled?: boolean;
  /** 首次展开状态已应用到 DOM 后回调（用于恢复滚动） */
  onExpandReady?: () => void;
};

export function FileTree({
  paths,
  activePaths = [],
  onSelectFile,
  onSelectFolder,
  dropHighlightDir,
  onDropHighlightDir,
  onDropFiles,
  onMovePath,
  onInternalDragStart,
  onInternalDragEnd,
  onContextMenu,
  renamingPath,
  renamingValue,
  onRenamingValueChange,
  onRenameCommit,
  onRenameCancel,
  onStartRename,
  disabled,
  onExpandReady,
}: Props) {
  const tree = useMemo(() => buildFileTree(paths), [paths]);
  const activePathSet = useMemo(() => new Set(activePaths), [activePaths]);
  /** 用户手势 / 默认规则 / 持久化恢复的展开态（唯一落盘来源） */
  const [userExpanded, setUserExpanded] = useState<Set<string>>(new Set());
  /** 会话中打开文件时的临时露出，不落盘 */
  const [sessionReveal, setSessionReveal] = useState<Set<string>>(new Set());
  const expanded = useMemo(() => {
    const next = new Set(userExpanded);
    for (const p of sessionReveal) next.add(p);
    return next;
  }, [userExpanded, sessionReveal]);
  const didHydrateRef = useRef(false);
  const didNotifyExpandReadyRef = useRef(false);
  /**
   * 仅在用户于本页主动选文件后，才允许 sessionReveal。
   * 避免刷新/新窗口时 activePaths 异步恢复把已折叠目录再次展开。
   */
  const allowSessionRevealRef = useRef(false);
  const [dragPath, setDragPath] = useState<string | null>(null);
  const dragPathRef = useRef<string | null>(null);

  function setDragSource(path: string | null) {
    dragPathRef.current = path;
    setDragPath(path);
    if (path === null) onInternalDragEnd?.();
  }

  function readDragSource(e: DragEvent): string {
    return (
      e.dataTransfer.getData("text/kb-path") ||
      e.dataTransfer.getData("text/plain") ||
      dragPathRef.current ||
      dragPath ||
      ""
    );
  }

  function setDragPayload(e: DragEvent, path: string) {
    e.dataTransfer.setData("text/kb-path", path);
    e.dataTransfer.setData("text/plain", path);
    e.dataTransfer.effectAllowed = "move";
    dragPathRef.current = path;
    setDragPath(path);
    onInternalDragStart?.();
  }

  useEffect(() => {
    if (tree.length === 0) return;

    if (!didHydrateRef.current) {
      didHydrateRef.current = true;
      allowSessionRevealRef.current = false;
      const stored = loadKbTreeUi();
      setUserExpanded(
        new Set(resolveExpandedFolderPaths(tree, stored?.expandedPaths)),
      );
      setSessionReveal(new Set());
      return;
    }

    const persisted = hasPersistedExpanded();
    setUserExpanded((prev) => {
      const nextPaths = nextUserExpandedAfterTreeChange(tree, prev, persisted);
      if (
        nextPaths.length === prev.size &&
        nextPaths.every((p) => prev.has(p))
      ) {
        return prev;
      }
      if (persisted) saveKbTreeExpandedIfPersisted(nextPaths);
      return new Set(nextPaths);
    });
    setSessionReveal((prev) => {
      if (prev.size === 0) return prev;
      return new Set(resolveExpandedFolderPaths(tree, [...prev]));
    });
  }, [tree]);

  useLayoutEffect(() => {
    if (!didHydrateRef.current || didNotifyExpandReadyRef.current) return;
    didNotifyExpandReadyRef.current = true;
    onExpandReady?.();
  }, [userExpanded, onExpandReady]);

  useEffect(() => {
    if (!didHydrateRef.current || !allowSessionRevealRef.current) return;
    setSessionReveal(new Set(collectAncestorFolderPaths(activePaths)));
  }, [activePaths]);

  function handleSelectFile(path: string, mods?: SelectMods) {
    allowSessionRevealRef.current = true;
    setSessionReveal(new Set(collectAncestorFolderPaths([path])));
    onSelectFile(path, mods);
  }

  function toggleFolder(path: string) {
    const closing = expanded.has(path);
    setUserExpanded((prev) => {
      const next = new Set(prev);
      if (closing) next.delete(path);
      else next.add(path);
      saveKbTreeExpanded([...next]);
      return next;
    });
    if (closing) {
      setSessionReveal((prev) => {
        if (!prev.has(path)) return prev;
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
    }
  }

  function handleFolderDrop(e: DragEvent, directory: string) {
    e.preventDefault();
    e.stopPropagation();
    onDropHighlightDir(null);
    if (disabled || isSystemLayerPath(directory)) return;
    if (e.dataTransfer.types.includes("Files")) {
      onDropFiles(e.dataTransfer, directory);
      return;
    }
    const from = readDragSource(e);
    if (from) void onMovePath(from, directory);
    setDragSource(null);
  }

  function allowDrop(e: DragEvent, directory: string) {
    if (disabled || isSystemLayerPath(directory)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = dropEffectForTransfer(e.dataTransfer);
    onDropHighlightDir(directory);
  }

  return (
    <div className={`file-tree${disabled ? " file-tree--busy" : ""}`}>
      {tree.length === 0 && <div className="file-tree-empty">暂无文档</div>}
      {tree.map((node) => (
        <TreeItem
          key={node.type === "file" ? node.path : `folder:${node.path}`}
          node={node}
          depth={0}
          expanded={expanded}
          activePathSet={activePathSet}
          dropHighlightDir={dropHighlightDir}
          dragPath={dragPath}
          setDragSource={setDragSource}
          readDragSource={readDragSource}
          setDragPayload={setDragPayload}
          onToggleFolder={toggleFolder}
          onSelectFile={handleSelectFile}
          onSelectFolder={onSelectFolder}
          onFolderDrop={handleFolderDrop}
          onFolderDragOver={allowDrop}
          onDropFiles={onDropFiles}
          onMovePath={onMovePath}
          onDropHighlightDir={onDropHighlightDir}
          onContextMenu={onContextMenu}
          renamingPath={renamingPath}
          renamingValue={renamingValue}
          onRenamingValueChange={onRenamingValueChange}
          onRenameCommit={onRenameCommit}
          onRenameCancel={onRenameCancel}
          onStartRename={onStartRename}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

function TreeItem({
  node,
  depth,
  expanded,
  activePathSet,
  dropHighlightDir,
  dragPath,
  setDragSource,
  readDragSource,
  setDragPayload,
  onToggleFolder,
  onSelectFile,
  onSelectFolder,
  onFolderDrop,
  onFolderDragOver,
  onDropFiles,
  onMovePath,
  onDropHighlightDir,
  onContextMenu,
  renamingPath,
  renamingValue,
  onRenamingValueChange,
  onRenameCommit,
  onRenameCancel,
  onStartRename,
  disabled,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  activePathSet: Set<string>;
  dropHighlightDir: string | null;
  dragPath: string | null;
  setDragSource: (p: string | null) => void;
  readDragSource: (e: DragEvent) => string;
  setDragPayload: (e: DragEvent, path: string) => void;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onSelectFolder?: (path: string, mods?: SelectMods) => void;
  onFolderDrop: (e: DragEvent, directory: string) => void;
  onFolderDragOver: (e: DragEvent, directory: string) => void;
  onDropFiles: (dataTransfer: DataTransfer, directory: string) => void;
  onMovePath: (fromPath: string, toDirectory: string) => void;
  onDropHighlightDir: (dir: string | null) => void;
  onContextMenu: (e: React.MouseEvent, ctx: FileTreeNodeContext) => void;
  renamingPath: string | null;
  renamingValue: string;
  onRenamingValueChange: (v: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onStartRename: (path: string, name: string) => void;
  disabled?: boolean;
}) {
  const pad = 8 + depth * 16;
  const systemLayer = isSystemLayerPath(node.path);

  if (node.type === "folder") {
    const isOpen = expanded.has(node.path);
    const dropActive = dropHighlightDir === node.path;
    const isRenaming = renamingPath === node.path;
    return (
      <>
        <div
          className={`file-tree-row folder${systemLayer ? " system-layer" : ""}${dropActive ? " drop-target" : ""}`}
          style={{ paddingLeft: pad }}
          draggable={!disabled && !systemLayer && !isRenaming}
          onDragStart={(e) => setDragPayload(e, node.path)}
          onDragEnd={() => setDragSource(null)}
          onClick={(e) => {
            if (
              !isRenaming &&
              onSelectFolder &&
              (e.ctrlKey || e.metaKey)
            ) {
              e.stopPropagation();
              onSelectFolder(node.path, {
                ctrlKey: e.ctrlKey,
                metaKey: e.metaKey,
              });
              return;
            }
            if (!isRenaming) onToggleFolder(node.path);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            onContextMenu(e, { node, kind: "folder", path: node.path });
          }}
          onDragOver={(e) => onFolderDragOver(e, node.path)}
          onDrop={(e) => onFolderDrop(e, node.path)}
        >
          <span className="file-tree-chevron">{isOpen ? "▼" : "▶"}</span>
          <span className="file-tree-icon">{isOpen ? "📂" : "📁"}</span>
          {isRenaming ? (
            <input
              className="file-tree-rename-input"
              value={renamingValue}
              onChange={(e) => onRenamingValueChange(e.target.value)}
              onBlur={onRenameCommit}
              onKeyDown={(e) => {
                if (e.key === "Enter") onRenameCommit();
                if (e.key === "Escape") onRenameCancel();
              }}
              autoFocus
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="file-tree-label">{node.name}</span>
          )}
        </div>
        {isOpen &&
          node.children.map((child) => (
            <TreeItem
              key={child.type === "file" ? child.path : `folder:${child.path}`}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              activePathSet={activePathSet}
              dropHighlightDir={dropHighlightDir}
              dragPath={dragPath}
              setDragSource={setDragSource}
              readDragSource={readDragSource}
              setDragPayload={setDragPayload}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
              onSelectFolder={onSelectFolder}
              onFolderDrop={onFolderDrop}
              onFolderDragOver={onFolderDragOver}
              onDropFiles={onDropFiles}
              onMovePath={onMovePath}
              onDropHighlightDir={onDropHighlightDir}
              onContextMenu={onContextMenu}
              renamingPath={renamingPath}
              renamingValue={renamingValue}
              onRenamingValueChange={onRenamingValueChange}
              onRenameCommit={onRenameCommit}
              onRenameCancel={onRenameCancel}
              onStartRename={onStartRename}
              disabled={disabled}
            />
          ))}
      </>
    );
  }

  const selected = activePathSet.has(node.path);
  const isRenaming = renamingPath === node.path;
  const isAttach = !isMarkdownPath(node.path);
  const fileParentDir = parentDirectoryFromPath(node.path);

  function handleFileDragOver(e: DragEvent) {
    if (disabled || isSystemLayerPath(node.path)) return;
    const files = e.dataTransfer.types.includes("Files");
    const kbPath = e.dataTransfer.types.includes("text/kb-path") ||
      e.dataTransfer.types.includes("text/plain");
    if (!files && !kbPath) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = dropEffectForTransfer(e.dataTransfer);
    onDropHighlightDir(fileParentDir);
  }

  function handleFileDrop(e: DragEvent) {
    if (disabled || isSystemLayerPath(node.path)) return;
    if (e.dataTransfer.types.includes("Files")) {
      e.preventDefault();
      e.stopPropagation();
      onDropHighlightDir(null);
      onDropFiles(e.dataTransfer, fileParentDir);
      return;
    }
    const from = readDragSource(e);
    if (!from) return;
    e.preventDefault();
    e.stopPropagation();
    onDropHighlightDir(null);
    void onMovePath(from, fileParentDir);
    setDragSource(null);
  }

  return (
    <div
      className={`file-tree-row file${systemLayer ? " system-layer" : ""}${selected ? " selected" : ""}`}
      style={{ paddingLeft: pad + 18 }}
      draggable={!disabled && !systemLayer && !isRenaming}
      onDragOver={handleFileDragOver}
      onDrop={handleFileDrop}
      onDragStart={(e) => setDragPayload(e, node.path)}
      onDragEnd={() => setDragSource(null)}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu(e, { node, kind: "file", path: node.path });
      }}
    >
      {isRenaming ? (
        <input
          className="file-tree-rename-input"
          value={renamingValue}
          onChange={(e) => onRenamingValueChange(e.target.value)}
          onBlur={onRenameCommit}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRenameCommit();
            if (e.key === "Escape") onRenameCancel();
          }}
          autoFocus
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <button
          type="button"
          className={`file-tree-file-btn${selected ? " file-tree-file-btn--active" : ""}`}
          onClick={(e) =>
            onSelectFile(node.path, {
              ctrlKey: e.ctrlKey,
              metaKey: e.metaKey,
              shiftKey: e.shiftKey,
            })
          }
          onDoubleClick={() => onStartRename(node.path, node.name)}
        >
          <span className="file-tree-icon">{isAttach ? "📎" : "📄"}</span>
          <span className="file-tree-label">{node.name}</span>
        </button>
      )}
    </div>
  );
}
