/** 知识库相对路径小工具。 */

export function isMarkdownPath(path: string) {
  return path.toLowerCase().endsWith(".md");
}

/** 路径最后一段（托盘标题等）。 */
export function pathBasename(path: string): string {
  return path.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? path;
}

export function parentDirectory(relPath: string): string {
  const norm = relPath.replace(/\\/g, "/");
  const idx = norm.lastIndexOf("/");
  return idx === -1 ? "" : norm.slice(0, idx);
}
