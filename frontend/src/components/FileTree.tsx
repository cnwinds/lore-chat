import { useEffect, useMemo, useState } from "react";
import {
  buildFileTree,
  collectFolderPaths,
  isSystemLayerPath,
  type TreeNode,
} from "../utils/fileTree";

type Props = {
  paths: string[];
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  selectionMode?: boolean;
  selectedPaths?: Set<string>;
  onToggleSelect?: (path: string, shiftKey?: boolean) => void;
  onPreviewFile?: (path: string) => void;
  onSelectFolderAll?: (paths: string[]) => void;
};

export function FileTree({
  paths,
  selectedPath,
  onSelectFile,
  selectionMode = false,
  selectedPaths = new Set(),
  onToggleSelect,
  onPreviewFile,
  onSelectFolderAll,
}: Props) {
  const tree = useMemo(() => buildFileTree(paths), [paths]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (tree.length > 0) {
      setExpanded(new Set(collectFolderPaths(tree)));
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

  return (
    <div className="file-tree">
      {tree.length === 0 && <div className="file-tree-empty">暂无文档</div>}
      {tree.map((node) => (
        <TreeItem
          key={node.type === "file" ? node.path : `folder:${node.path}`}
          node={node}
          depth={0}
          expanded={expanded}
          selectedPath={selectedPath}
          selectionMode={selectionMode}
          selectedPaths={selectedPaths}
          onToggleFolder={toggleFolder}
          onSelectFile={onSelectFile}
          onToggleSelect={onToggleSelect}
          onPreviewFile={onPreviewFile}
          onSelectFolderAll={onSelectFolderAll}
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
  selectionMode,
  selectedPaths,
  onToggleFolder,
  onSelectFile,
  onToggleSelect,
  onPreviewFile,
  onSelectFolderAll,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  selectedPath: string | null;
  selectionMode: boolean;
  selectedPaths: Set<string>;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string) => void;
  onToggleSelect?: (path: string, shiftKey?: boolean) => void;
  onPreviewFile?: (path: string) => void;
  onSelectFolderAll?: (paths: string[]) => void;
}) {
  const pad = 8 + depth * 16;
  const systemLayer = isSystemLayerPath(node.path);

  if (node.type === "folder") {
    const isOpen = expanded.has(node.path);
    const selectablePaths = selectionMode ? collectSelectableMdFiles(node.children) : [];
    return (
      <>
        <div
          className={`file-tree-row folder${systemLayer ? " system-layer" : ""}`}
          style={{ paddingLeft: pad }}
          onClick={() => onToggleFolder(node.path)}
        >
          <span className="file-tree-chevron">{isOpen ? "▼" : "▶"}</span>
          <span className="file-tree-icon">{isOpen ? "📂" : "📁"}</span>
          <span className="file-tree-label">{node.name}</span>
          {selectionMode && selectablePaths.length > 0 && onSelectFolderAll && (
            <button
              type="button"
              className="file-tree-folder-all-btn"
              onClick={(e) => {
                e.stopPropagation();
                onSelectFolderAll(selectablePaths);
              }}
            >
              全选
            </button>
          )}
        </div>
        {isOpen &&
          node.children.map((child) => (
            <TreeItem
              key={child.type === "file" ? child.path : `folder:${child.path}`}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedPath={selectedPath}
              selectionMode={selectionMode}
              selectedPaths={selectedPaths}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
              onToggleSelect={onToggleSelect}
              onPreviewFile={onPreviewFile}
              onSelectFolderAll={onSelectFolderAll}
            />
          ))}
      </>
    );
  }

  const selected = selectedPath === node.path;
  const checked = selectedPaths.has(node.path);
  const disabledSelect = systemLayer;

  if (selectionMode) {
    return (
      <div
        className={`file-tree-row file${systemLayer ? " system-layer" : ""}${checked ? " checked" : ""}`}
        style={{ paddingLeft: pad + 18 }}
        onClick={(e) => {
          if (disabledSelect || !onToggleSelect) return;
          onToggleSelect(node.path, e.shiftKey);
        }}
        onDoubleClick={() => onPreviewFile?.(node.path)}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={disabledSelect}
          readOnly
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect?.(node.path, e.shiftKey);
          }}
        />
        <span className="file-tree-icon">📄</span>
        <span className="file-tree-label">{node.name}</span>
        {onPreviewFile && (
          <button
            type="button"
            className="file-tree-preview-btn"
            title="预览文档"
            onClick={(e) => {
              e.stopPropagation();
              onPreviewFile(node.path);
            }}
          >
            👁
          </button>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`file-tree-row file${systemLayer ? " system-layer" : ""}${selected ? " selected" : ""}`}
      style={{ paddingLeft: pad + 18 }}
      onClick={() => onSelectFile(node.path)}
    >
      <span className="file-tree-icon">📄</span>
      <span className="file-tree-label">{node.name}</span>
    </button>
  );
}

function collectSelectableMdFiles(nodes: TreeNode[]): string[] {
  const out: string[] = [];
  for (const node of nodes) {
    if (node.type === "folder") {
      out.push(...collectSelectableMdFiles(node.children));
      continue;
    }
    if (!node.path.endsWith(".md")) continue;
    if (isSystemLayerPath(node.path)) continue;
    out.push(node.path);
  }
  return out;
}
