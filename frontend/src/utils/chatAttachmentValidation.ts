import type { PendingFile } from "../types/composer";
import {
  MAX_VIDEO_UPLOAD_BYTES,
  MAX_VIDEOS_PER_MESSAGE,
  isVideoFile,
} from "./kbVideoUrls";

export function validatePendingAttachments(
  files: PendingFile[],
  maxVideos: number = MAX_VIDEOS_PER_MESSAGE,
): string | null {
  let videoCount = 0;
  const limit = Math.max(1, maxVideos);
  for (const f of files) {
    if (isVideoFile(f.file, f.name)) {
      videoCount += 1;
      if (f.size > MAX_VIDEO_UPLOAD_BYTES) {
        return `视频「${f.name}」超过 ${Math.round(MAX_VIDEO_UPLOAD_BYTES / (1024 * 1024))}MB 上限`;
      }
    }
  }
  if (videoCount > limit) {
    return `每条消息最多发送 ${limit} 个视频`;
  }
  return null;
}

export function pendingHasVideo(files: PendingFile[]): boolean {
  return files.some((f) => isVideoFile(f.file, f.name));
}
