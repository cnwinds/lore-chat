/** 聊天媒体落盘路径约定（与 backend `kb_media_paths` 对齐）。 */

export const MEDIA_ROOT = "媒体";
export const MEDIA_UPLOADS = "上传";
export const MEDIA_GENERATED = "生成";

export function utcYear(d: Date = new Date()): string {
  return String(d.getUTCFullYear());
}

export function mediaUploadDir(year?: string): string {
  return `${MEDIA_ROOT}/${MEDIA_UPLOADS}/${year ?? utcYear()}`;
}

export function mediaGeneratedDir(year?: string): string {
  return `${MEDIA_ROOT}/${MEDIA_GENERATED}/${year ?? utcYear()}`;
}

export function isMediaPath(rel: string): boolean {
  const norm = (rel || "").replace(/\\/g, "/").replace(/^\/+/, "");
  return norm === MEDIA_ROOT || norm.startsWith(`${MEDIA_ROOT}/`);
}

/** 规范化知识库相对路径（去反斜杠与首尾多余斜杠）。 */
export function normalizeKbRel(rel: string): string {
  return (rel || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
}

/**
 * 是否为媒体树下的「末级目录」：路径在媒体下，且树节点无子文件夹。
 * 中间层（媒体、媒体/生成）点选只展开；末级（如媒体/生成/2026）打开浮窗图库。
 */
export function isMediaLeafDirectory(
  dirPath: string,
  hasChildFolders: boolean,
): boolean {
  const norm = normalizeKbRel(dirPath);
  if (!norm || norm === MEDIA_ROOT) return false;
  if (!isMediaPath(norm)) return false;
  return !hasChildFolders;
}

/** 列出目录下的直接子文件（不含子目录内文件）。 */
export function listDirectChildren(
  dirPath: string,
  allPaths: string[],
): string[] {
  const dir = normalizeKbRel(dirPath);
  const prefix = dir ? `${dir}/` : "";
  return allPaths
    .map(normalizeKbRel)
    .filter((p) => {
      if (!p.startsWith(prefix)) return false;
      const rest = p.slice(prefix.length);
      return rest.length > 0 && !rest.includes("/");
    })
    .sort((a, b) => a.localeCompare(b, "zh"));
}
