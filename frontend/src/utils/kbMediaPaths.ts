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
