/** 从 chat 链配置推断多模态上传限制与能力（与后端 router 语义对齐）。 */

import {
  resolveModelCaps,
  type ModelCapsFields,
} from "../components/settings/modelCapabilities";

export type ChainMediaCaps = {
  image: boolean;
  maxImages: number | null;
  video: boolean;
  maxVideos: number;
  videoWire: "data" | "url";
};

export type ChainMediaLimits = {
  videoSupported: boolean;
  maxVideos: number;
  imageSupported: boolean;
  maxImages: number | null;
  videoWireData: boolean;
};

type ChainModel = {
  model?: string;
  base_url?: string | null;
  image?: boolean;
  max_images?: number | null;
  video?: boolean;
  max_videos?: number;
  video_wire?: "data" | "url";
};

function asChainModels(raw: unknown): ChainModel[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((m): m is ChainModel => !!m && typeof m === "object");
}

/** 合并 settings 已存字段与 catalog lookup 结果。 */
export function mergeCandidateMediaCaps(
  saved: Pick<ChainModel, "image" | "max_images" | "video" | "max_videos" | "video_wire">,
  catalog: Pick<
    ModelCapsFields,
    "image" | "max_images" | "video" | "max_videos" | "video_wire"
  >,
): ChainMediaCaps {
  return {
    image: typeof saved.image === "boolean" ? saved.image : catalog.image,
    maxImages:
      typeof saved.max_images === "number" && saved.max_images > 0
        ? saved.max_images
        : catalog.max_images,
    video: typeof saved.video === "boolean" ? saved.video : catalog.video,
    maxVideos:
      typeof saved.max_videos === "number" && saved.max_videos > 0
        ? saved.max_videos
        : catalog.max_videos,
    videoWire:
      saved.video_wire === "url" || saved.video_wire === "data"
        ? saved.video_wire
        : catalog.video_wire,
  };
}

function aggregateMaxImages(caps: ChainMediaCaps[]): number | null {
  const imageOnes = caps.filter((c) => c.image);
  if (imageOnes.length === 0) return null;
  const limits = imageOnes
    .map((c) => c.maxImages)
    .filter((n): n is number => typeof n === "number" && n > 0);
  if (limits.length === 0) return null;
  return Math.min(...limits);
}

/** 聚合链级能力：视频取 video 候选的最小 maxVideos；识图取 image 候选的最小 maxImages。 */
export function aggregateChainMediaCaps(caps: ChainMediaCaps[]): ChainMediaLimits {
  const videoOnes = caps.filter((c) => c.video);
  const imageOnes = caps.filter((c) => c.image);
  return {
    videoSupported: videoOnes.length > 0,
    maxVideos:
      videoOnes.length === 0
        ? 1
        : Math.min(...videoOnes.map((c) => Math.max(1, c.maxVideos))),
    imageSupported: imageOnes.length > 0,
    maxImages: aggregateMaxImages(caps),
    videoWireData:
      videoOnes.length > 0 && videoOnes.some((c) => c.videoWire === "data"),
  };
}

/** 经 catalog lookup 解析 chat 链多模态能力（CONTEXT 唯一真相）。 */
export async function resolveChainMediaCapsFromSettings(
  chatModels: unknown,
): Promise<ChainMediaLimits> {
  const models = asChainModels(chatModels);
  if (models.length === 0) {
    return {
      videoSupported: false,
      maxVideos: 1,
      imageSupported: false,
      maxImages: null,
      videoWireData: false,
    };
  }
  const merged = await Promise.all(
    models.map(async (m) => {
      const model = String(m.model || "").trim();
      if (!model) {
        return {
          image: false,
          maxImages: null,
          video: false,
          maxVideos: 1,
          videoWire: "data" as const,
        };
      }
      const catalog = await resolveModelCaps(
        model,
        m.base_url?.trim() || undefined,
      );
      return mergeCandidateMediaCaps(m, catalog);
    }),
  );
  return aggregateChainMediaCaps(merged);
}
