/** 从 chat 链配置推断多模态上传限制与能力（与后端 router 语义对齐）。 */

import {
  resolveModelCaps,
  type ModelCapsFields,
} from "../components/settings/modelCapabilities";

export type ChainMediaCaps = {
  video: boolean;
  maxVideos: number;
};

type ChainModel = {
  model?: string;
  base_url?: string | null;
  video?: boolean;
  max_videos?: number;
};

function asChainModels(raw: unknown): ChainModel[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((m): m is ChainModel => !!m && typeof m === "object");
}

/** 合并 settings 已存字段与 catalog lookup 结果。 */
export function mergeCandidateMediaCaps(
  saved: Pick<ChainModel, "video" | "max_videos">,
  catalog: Pick<ModelCapsFields, "video" | "max_videos">,
): ChainMediaCaps {
  return {
    video: typeof saved.video === "boolean" ? saved.video : catalog.video,
    maxVideos:
      typeof saved.max_videos === "number" && saved.max_videos > 0
        ? saved.max_videos
        : catalog.max_videos,
  };
}

/** 聚合链级能力：任一候选可处理视频；上限取 video 候选的最小 maxVideos。 */
export function aggregateChainMediaCaps(caps: ChainMediaCaps[]): {
  videoSupported: boolean;
  maxVideos: number;
} {
  const videoOnes = caps.filter((c) => c.video);
  if (videoOnes.length === 0) {
    return { videoSupported: false, maxVideos: 1 };
  }
  return {
    videoSupported: true,
    maxVideos: Math.min(
      ...videoOnes.map((c) => Math.max(1, c.maxVideos)),
    ),
  };
}

function chainModelsToCaps(chatModels: unknown): ChainMediaCaps[] {
  return asChainModels(chatModels).map((m) =>
    mergeCandidateMediaCaps(m, {
      video: Boolean(m.video),
      max_videos:
        typeof m.max_videos === "number" && m.max_videos > 0
          ? m.max_videos
          : 1,
    }),
  );
}

/** 对已 enrich 的链字段做同步聚合（单测 / 无 lookup 场景）。 */
export function chatChainSupportsVideo(chatModels: unknown): boolean {
  return aggregateChainMediaCaps(chainModelsToCaps(chatModels)).videoSupported;
}

export function chatChainMaxVideos(chatModels: unknown): number {
  return aggregateChainMediaCaps(chainModelsToCaps(chatModels)).maxVideos;
}

/** 经 catalog lookup 解析 chat 链多模态能力（CONTEXT 唯一真相）。 */
export async function resolveChainMediaCapsFromSettings(
  chatModels: unknown,
): Promise<{ videoSupported: boolean; maxVideos: number }> {
  const models = asChainModels(chatModels);
  if (models.length === 0) {
    return { videoSupported: false, maxVideos: 1 };
  }
  const merged = await Promise.all(
    models.map(async (m) => {
      const model = String(m.model || "").trim();
      if (!model) {
        return { video: false, maxVideos: 1 };
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
