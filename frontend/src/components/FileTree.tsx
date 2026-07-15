import { useEffect, useMemo, useState } from "react";
import {
  buildFileTree,
  collectDefaultExpandedFolderPaths,
  isSystemLayerPath,
  type TreeNode,
} from "../utils/fileTree";

type SelectMods = { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean };

type Props = {
  paths: string[];
  selectedPath: string | null;
  onSelectFile: (path: string, mods?: SelectMods) => void;
};

export function FileTree({ paths, selectedPath, onSelectFile }: Props) {
  const tree = useMemo(() => buildFileTree(paths), [paths]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

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
          onToggleFolder={toggleFolder}
          onSelectFile={onSelectFile}
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
  onToggleFolder,
  onSelectFile,
}: {
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  selectedPath: string | null;
  onToggleFolder: (path: string) => void;
  onSelectFile: (path: string, mods?: SelectMods) => void;
}) {
  const pad = 8 + depth * 16;
  const systemLayer = isSystemLayerPath(node.path);

  if (node.type === "folder") {
    const isOpen = expanded.has(node.path);
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
        </div>
        {isOpen &&
          node.children.map((child) => (
            <TreeItem
              key={child.type === "file" ? child.path : `folder:${child.path}`}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedPath={selectedPath}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
            />
          ))}
      </>
    );
  }

  const selected = selectedPath === node.path;

  return (
    <button
      type="button"
      className={`file-tree-row file${systemLayer ? " system-layer" : ""}${selected ? " selected" : ""}`}
      style={{ paddingLeft: pad + 18 }}
      onClick={(e) =>
        onSelectFile(node.path, {
          ctrlKey: e.ctrlKey,
          metaKey: e.metaKey,
          shiftKey: e.shiftKey,
        })
      }
    >
      <span className="file-tree-icon">📄</span>
      <span className="file-tree-label">{node.name}</span>
    </button>
  );
}
