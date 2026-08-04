import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  buildFileTree,
  collectDefaultExpandedFolderPaths,
  isSystemLayerPath,
  type TreeNode,
} from "../utils/fileTree";
import { isMarkdownPath } from "../api";

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

export type FileTreeNodeContext = {
  node: TreeNode;
  kind: "file" | "folder";
  path: string;
};

type Props = {
  paths: string[];
  selectedPath: string | null;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  dropHighlightDir: string | null;
  onDropHighlightDir: (dir: string | null) => void;
  onDropFiles: (files: FileList, directory: string) => void;
  onMovePath: (fromPath: string, toDirectory: string) => void;
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
  selectedPath,
  onSelectFile,
  dropHighlightDir,
  onDropHighlightDir,
  onDropFiles,
  onMovePath,
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
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [dragPath, setDragPath] = useState<string | null>(null);

  useEffect(() => {
    if (tree.length > 0) {
      setExpanded(new Set(collectDefaultExpandedFolderPaths(tree)));
    }
  }, [tree]);

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
    if (e.dataTransfer.files?.length) {
      onDropFiles(e.dataTransfer.files, directory);
      return;
    }
    const from = e.dataTransfer.getData("text/kb-path") || dragPath;
    if (from) onMovePath(from, directory);
    setDragPath(null);
  }

  function allowDrop(e: DragEvent, directory: string) {
    if (disabled || isSystemLayerPath(directory)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
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
          selectedPath={selectedPath}
          dropHighlightDir={dropHighlightDir}
          dragPath={dragPath}
          setDragPath={setDragPath}
          onToggleFolder={toggleFolder}
          onSelectFile={onSelectFile}
          onFolderDrop={handleFolderDrop}
          onFolderDragOver={allowDrop}
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
  selectedPath,
  dropHighlightDir,
  dragPath,
  setDragPath,
  onToggleFolder,
  onSelectFile,
  onFolderDrop,
  onFolderDragOver,
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
  selectedPath: string | null;
  dropHighlightDir: string | null;
  dragPath: string | null;
  setDragPath: (p: string | null) => void;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string, mods?: SelectMods) => void;
  onFolderDrop: (e: DragEvent, directory: string) => void;
  onFolderDragOver: (e: DragEvent, directory: string) => void;
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
    return (
      <>
        <div
          className={`file-tree-row folder${systemLayer ? " system-layer" : ""}${dropActive ? " drop-target" : ""}`}
          style={{ paddingLeft: pad }}
          onClick={() => onToggleFolder(node.path)}
          onContextMenu={(e) => {
            e.preventDefault();
            onContextMenu(e, { node, kind: "folder", path: node.path });
          }}
          onDragOver={(e) => onFolderDragOver(e, node.path)}
          onDragLeave={() => onDropHighlightDir(null)}
          onDrop={(e) => onFolderDrop(e, node.path)}
        >
          <span className="file-tree-chevron">{isOpen ? "▼" : "▶"}</span>
          <span className="file-tree-icon">{isOpen ? "📂" : "📁"}</span>
          <span className="file-tree-label">{node.name}</span>
        </div>
        {isOpen &&
          node.children.map((child) => (
            <TreeItem
              key={child.type === "file" ? child.path : `folder:${child.path}`}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedPath={selectedPath}
              dropHighlightDir={dropHighlightDir}
              dragPath={dragPath}
              setDragPath={setDragPath}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
              onFolderDrop={onFolderDrop}
              onFolderDragOver={onFolderDragOver}
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

  const selected = selectedPath === node.path;
  const isRenaming = renamingPath === node.path;
  const isAttach = !isMarkdownPath(node.path);

  return (
    <div
      className={`file-tree-row file${systemLayer ? " system-layer" : ""}${selected ? " selected" : ""}`}
      style={{ paddingLeft: pad + 18 }}
      draggable={!disabled && !systemLayer && !isRenaming}
      onDragStart={(e) => {
        setDragPath(node.path);
        e.dataTransfer.setData("text/kb-path", node.path);
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragEnd={() => setDragPath(null)}
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
          className="file-tree-file-btn"
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
