/** 视频附件：MIME / 路径启发式（与 kbImageUrls 对称）。 */

const VIDEO_EXT = /\.(mp4|mpeg|mpg|mov|webm|m4v)$/i;

export function isLikelyVideoPath(path: string): boolean {
  return VIDEO_EXT.test(path.split("?")[0] || path);
}

export function isVideoFile(file: File, name?: string): boolean {
  if (file.type.startsWith("video/")) return true;
  return isLikelyVideoPath(name ?? file.name);
}

export function videoExtFromFile(file: File, name?: string): string {
  const n = name ?? file.name;
  const m = n.match(VIDEO_EXT);
  if (m) return m[0].toLowerCase();
  const mime = file.type.toLowerCase();
  if (mime === "video/mp4") return ".mp4";
  if (mime === "video/webm") return ".webm";
  if (mime === "video/quicktime") return ".mov";
  if (mime === "video/mpeg") return ".mpeg";
  return ".mp4";
}

/** 单条消息默认最多 1 个视频（与后端 max_videos 默认一致）。 */
export const MAX_VIDEOS_PER_MESSAGE = 1;

/** 上传大小软限制（字节；与 backend/app/models/media.py MAX_VIDEO_UPLOAD_BYTES 对齐）。 */
export const MAX_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024;