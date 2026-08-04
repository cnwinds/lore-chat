/** 单文件或目录前缀移动后，更新文档路径。 */
export function remapKbPath(path: string, from: string, to: string): string {
  if (path === from) return to;
  if (from && path.startsWith(`${from}/`)) {
    return to + path.slice(from.length);
  }
  return path;
}

export function remapKbPathNullable(
  path: string | null,
  from: string,
  to: string,
): string | null {
  if (path === null) return null;
  return remapKbPath(path, from, to);
}
