/** 聊天附件导入：重名时由调用方弹窗（覆盖 / 重命名）。 */

import { kbImport } from "../api";
import { kbMutateWithConflictRetry } from "../lib/kbMutateWithConflictRetry";
import type { KbConflictPrompt } from "../lib/kbMutateWithConflictRetry";
import { mediaUploadDir } from "./kbMediaPaths";
import { imageExtFromFile, isImageFile } from "./kbImageUrls";
import { isVideoFile, videoExtFromFile } from "./kbVideoUrls";

function bytesToHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function hashNamedFilename(file: File, ext: string): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = bytesToHex(digest).slice(0, 32);
  return `${hex}${ext}`;
}

/** 图片/视频：sha256 前 32 hex + 扩展名；其它文件保留原名。 */
export async function chatAttachmentFilename(file: File): Promise<string> {
  if (isImageFile(file)) {
    return hashNamedFilename(file, imageExtFromFile(file));
  }
  if (isVideoFile(file)) {
    return hashNamedFilename(file, videoExtFromFile(file));
  }
  return file.name || "upload.bin";
}

/**
 * 将文件导入知识库供本轮附件使用。
 * 同内容图片 → 同路径，后端幂等复用；重名冲突走 onConflict 弹窗。
 */
export async function importChatAttachment(
  file: File,
  directory: string = mediaUploadDir(),
  opts: { onConflict: (ctx: KbConflictPrompt) => void },
): Promise<string> {
  const initialFilename = await chatAttachmentFilename(file);
  const rel = await kbMutateWithConflictRetry({
    initialFilename,
    onConflict: opts.onConflict,
    run: async ({ filename, overwrite }) => {
      const r = await kbImport(file, directory, filename, undefined, overwrite);
      return r.rel_path;
    },
  });
  if (!rel) {
    throw new Error("已取消上传");
  }
  return rel;
}
