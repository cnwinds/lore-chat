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

  const sortNodes = (nodes: TreeNode[]): TreeNode[] =>
    [...nodes]
      .sort((a, b) => {
        if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-CN");
      })
      .map((n) =>
        n.type === "folder" ? { ...n, children: sortNodes(n.children) } : n,
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
