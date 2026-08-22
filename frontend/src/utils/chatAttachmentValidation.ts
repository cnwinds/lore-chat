import type { PendingFile } from "../types/composer";
import { isImageFile } from "./kbImageUrls";
import {
  MAX_VIDEO_DATA_WIRE_BYTES,
  MAX_VIDEO_UPLOAD_BYTES,
  MAX_VIDEOS_PER_MESSAGE,
  isVideoFile,
} from "./kbVideoUrls";
import type { ChainMediaLimits } from "./chatChainMedia";

export type AttachmentValidationLimits = {
  maxVideos?: number;
  maxImages?: number | null;
};

const MB = 1024 * 1024;

export function validatePendingAttachments(
  files: PendingFile[],
  limits: AttachmentValidationLimits = {},
): string | null {
  const maxVideos = Math.max(1, limits.maxVideos ?? MAX_VIDEOS_PER_MESSAGE);
  const maxImages = limits.maxImages;
  let videoCount = 0;
  let visionImageCount = 0;

  for (const f of files) {
    if (isVideoFile(f.file, f.name)) {
      videoCount += 1;
      if (f.size > MAX_VIDEO_UPLOAD_BYTES) {
        return `视频「${f.name}」超过 ${Math.round(MAX_VIDEO_UPLOAD_BYTES / MB)}MB 上限`;
      }
    } else if (isImageFile(f.file, f.name)) {
      visionImageCount += 1;
    }
  }

  if (videoCount > maxVideos) {
    return `每条消息最多发送 ${maxVideos} 个视频`;
  }
  if (
    maxImages != null &&
    maxImages > 0 &&
    visionImageCount > maxImages
  ) {
    return `每条消息最多向模型发送 ${maxImages} 张识图图片`;
  }
  return null;
}

export function pendingHasVideo(files: PendingFile[]): boolean {
  return files.some((f) => isVideoFile(f.file, f.name));
}

export function pendingVisionImageCount(files: PendingFile[]): number {
  return files.filter((f) => isImageFile(f.file, f.name)).length;
}

/** Composer 托盘：链能力与待发送附件对齐提示（CONTEXT L89）。 */
export function buildComposerMediaHints(
  files: PendingFile[],
  caps: ChainMediaLimits,
): string[] {
  if (files.length === 0) return [];

  const hints: string[] = [];
  const videoCount = files.filter((f) => isVideoFile(f.file, f.name)).length;
  const imageCount = pendingVisionImageCount(files);

  if (videoCount > 0) {
    if (!caps.videoSupported) {
      hints.push(
        "当前对话模型链未配置视频能力，视频将仅作附件保存，不会送入模型。",
      );
    }
    hints.push(
      `视频：每条消息最多 ${caps.maxVideos} 个，单文件不超过 ${Math.round(MAX_VIDEO_UPLOAD_BYTES / MB)}MB。`,
    );
    if (caps.videoWireData) {
      const large = files.some(
        (f) =>
          isVideoFile(f.file, f.name) &&
          f.size > MAX_VIDEO_DATA_WIRE_BYTES,
      );
      if (large) {
        hints.push(
          `超过 ${Math.round(MAX_VIDEO_DATA_WIRE_BYTES / MB)}MB 的视频在配置了 public_base_url 时将优先使用签名 URL 传输。`,
        );
      }
    }
  }

  if (imageCount > 0 && caps.imageSupported && caps.maxImages != null) {
    hints.push(
      `识图图片：每条消息最多向模型发送 ${caps.maxImages} 张（超出部分仅作附件保存）。`,
    );
  }

  return hints;
}
