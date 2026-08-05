import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  buildFileTree,
  collectDefaultExpandedFolderPaths,
  isSystemLayerPath,
  type TreeNode,
} from "../utils/fileTree";
import { isMarkdownPath } from "../api";
import { dropEffectForTransfer } from "../utils/droppedFiles";

function parentDirectoryFromPath(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx);
}

function folderPathsContainingFile(filePath: string): string[] {
  const parts = filePath.split("/").filter(Boolean);
  if (parts.length <= 1) return [];
  const folders: string[] = [];
  for (let i = 0; i < parts.length - 1; i++) {
    folders.push(parts.slice(0, i + 1).join("/"));
  }
  return folders;
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
}: Props) {
  const tree = useMemo(() => buildFileTree(paths), [paths]);
  const activePathSet = useMemo(() => new Set(activePaths), [activePaths]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
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
    if (tree.length > 0) {
      setExpanded(new Set(collectDefaultExpandedFolderPaths(tree)));
    }
  }, [tree]);

  useEffect(() => {
    if (!activePaths.length) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const filePath of activePaths) {
        for (const folder of folderPathsContainingFile(filePath)) {
          next.add(folder);
        }
      }
      return next;
    });
  }, [activePaths]);

  function toggleFolder(path: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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
          onSelectFile={onSelectFile}
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
