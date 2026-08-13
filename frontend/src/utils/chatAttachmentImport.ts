/** 聊天附件导入：冲突时自动换名；图片按内容哈希命名以便同图幂等复用。 */

import type { ApiError } from "../api";
import { kbImport } from "../api";
import { imageExtFromFile, isImageFile } from "./kbImageUrls";

const CHAT_ATTACH_DIR = "未分类";
const MAX_CONFLICT_RETRIES = 8;

function bytesToHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** 图片：sha256 前 32 hex + 扩展名；其它文件保留原名。 */
export async function chatAttachmentFilename(file: File): Promise<string> {
  if (!isImageFile(file)) {
    return file.name || "upload.bin";
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = bytesToHex(digest).slice(0, 32);
  return `${hex}${imageExtFromFile(file)}`;
}

/**
 * 将文件导入知识库供本轮附件使用。
 * 同内容图片 → 同路径，后端幂等复用；其它冲突自动换名。
 */
export async function importChatAttachment(
  file: File,
  directory: string = CHAT_ATTACH_DIR,
): Promise<string> {
  let filename: string | undefined = await chatAttachmentFilename(file);
  let lastErr: unknown;
  for (let i = 0; i < MAX_CONFLICT_RETRIES; i++) {
    try {
      const r = await kbImport(file, directory, filename);
      return r.rel_path;
    } catch (e) {
      lastErr = e;
      const err = e as ApiError;
      const suggested = err.pathExists?.suggested_filename;
      if (err.status === 409 && err.pathExists && suggested) {
        filename = suggested;
        continue;
      }
      throw e;
    }
  }
  throw lastErr instanceof Error
    ? lastErr
    : new Error("上传失败：文件名冲突过多");
}
