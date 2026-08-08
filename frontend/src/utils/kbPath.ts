/** 知识库相对路径小工具。 */

export function isMarkdownPath(path: string) {
  return path.toLowerCase().endsWith(".md");
}

export function parentDirectory(relPath: string): string {
  const norm = relPath.replace(/\\/g, "/");
  const idx = norm.lastIndexOf("/");
  return idx === -1 ? "" : norm.slice(0, idx);
}

