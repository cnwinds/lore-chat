/** 系统控制层目录名，与 backend `system_layer_dir` 保持一致 */
export const SYSTEM_LAYER_DIR = "系统";

/** 系统层文件显示顺序：心法在上，戒律在下（与 backend SystemLayer.compose 一致） */
const SYSTEM_LAYER_FILE_ORDER = ["心法.md", "戒律.md"];

export function isSystemLayerPath(path: string): boolean {
  return path === SYSTEM_LAYER_DIR || path.startsWith(`${SYSTEM_LAYER_DIR}/`);
}

export type FileNode = { type: "file"; name: string; path: string };
export type FolderNode = {
  type: "folder";
  name: string;
  path: string;
  children: TreeNode[];
};
export type TreeNode = FileNode | FolderNode;

export function buildFileTree(paths: string[]): TreeNode[] {
  const root: FolderNode = { type: "folder", name: "", path: "", children: [] };

  for (const rel of [...paths].sort()) {
    const parts = rel.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const nodePath = parts.slice(0, i + 1).join("/");

      if (isFile) {
        current.children.push({ type: "file", name: part, path: rel });
      } else {
        let folder = current.children.find(
          (c): c is FolderNode => c.type === "folder" && c.name === part,
        );
        if (!folder) {
          folder = { type: "folder", name: part, path: nodePath, children: [] };
          current.children.push(folder);
        }
        current = folder;
      }
    }
  }

  const sortNodes = (nodes: TreeNode[], parentPath = ""): TreeNode[] =>
    [...nodes]
      .sort((a, b) => {
        if (parentPath === "") {
          const aSystem = a.type === "folder" && a.name === SYSTEM_LAYER_DIR;
          const bSystem = b.type === "folder" && b.name === SYSTEM_LAYER_DIR;
          if (aSystem !== bSystem) return aSystem ? -1 : 1;
        }
        if (parentPath === SYSTEM_LAYER_DIR) {
          const orderA = SYSTEM_LAYER_FILE_ORDER.indexOf(a.name);
          const orderB = SYSTEM_LAYER_FILE_ORDER.indexOf(b.name);
          const rankA = orderA === -1 ? SYSTEM_LAYER_FILE_ORDER.length : orderA;
          const rankB = orderB === -1 ? SYSTEM_LAYER_FILE_ORDER.length : orderB;
          if (rankA !== rankB) return rankA - rankB;
        }
        if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-CN");
      })
      .map((n) =>
        n.type === "folder" ? { ...n, children: sortNodes(n.children, n.path) } : n,
      );

  return sortNodes(root.children);
}

export function collectFolderPaths(nodes: TreeNode[]): string[] {
  const paths: string[] = [];
  for (const n of nodes) {
    if (n.type === "folder") {
      paths.push(n.path);
      paths.push(...collectFolderPaths(n.children));
    }
  }
  return paths;
}

/** 默认展开的文件夹：前 2 层展开，第 3 层及以下折叠；系统控制层目录保持折叠 */
export function collectDefaultExpandedFolderPaths(nodes: TreeNode[]): string[] {
  return collectFolderPaths(nodes).filter((p) => {
    if (p === SYSTEM_LAYER_DIR) return false;
    const depth = p.split("/").filter(Boolean).length;
    return depth <= 2;
  });
}
