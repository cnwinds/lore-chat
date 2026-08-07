/** 文件夹拖放移动的目标校验（from 为目录路径，不含文件名）。 */
export function isKbFolderMoveInvalid(
  fromPath: string,
  toDirectory: string,
): boolean {
  const from = fromPath.replace(/\\/g, "/").replace(/\/+$/, "");
  const to = toDirectory.replace(/\\/g, "/").replace(/\/+$/, "");
  if (!from) return false;
  if (to === from) return true;
  if (to.startsWith(`${from}/`)) return true;
  return false;
}

export function filesUnderKbDirectory(
  folder: string,
  docs: string[],
): string[] {
  const norm = folder.replace(/\\/g, "/").replace(/\/+$/, "");
  if (!norm) return [];
  const prefix = `${norm}/`;
  return docs.filter((p) => p.startsWith(prefix)).sort();
}

/** 树节点为文件夹（含空目录：树列表无子路径时仍可能为目录）。 */
export function isKbDirectoryPath(path: string, docs: string[]): boolean {
  const norm = path.replace(/\\/g, "/").replace(/\/+$/, "");
  if (!norm || docs.includes(norm)) return false;
  if (filesUnderKbDirectory(norm, docs).length > 0) return true;
  const base = norm.split("/").pop() ?? "";
  return base.length > 0 && !base.includes(".");
}

export function targetFolderRoot(
  fromPath: string,
  toDirectory: string,
  toName?: string,
): string {
  const name = toName ?? fromPath.split("/").pop() ?? "";
  const base = toDirectory.replace(/\\/g, "/").replace(/\/+$/, "");
  if (!base) return name;
  return `${base}/${name}`;
}
