import { lookupModelCapabilities, type ModelCapabilitiesResponse, type ModelCatalogItem } from "../../api";
import type { ModelCandidateDraft } from "./providerPresets";
import { pickEffortInOptions } from "./modelChainDrafts";

export type ModelCapsFields = Pick<
  ModelCandidateDraft,
  | "image"
  | "video"
  | "thinking"
  | "effort"
  | "effort_options"
  | "image_wire"
  | "video_wire"
  | "max_videos"
  | "max_images"
  | "thinking_protocol"
>;

/** lookup 失败或空模型名时的保守默认（无前端前缀表）。 */
export function conservativeModelCaps(): ModelCapsFields {
  return {
    image: false,
    video: false,
    thinking: false,
    effort: "medium",
    effort_options: [],
    image_wire: "data",
    video_wire: "data",
    max_videos: 1,
    max_images: null,
    thinking_protocol: "none",
  };
}

export function capsFromLookupResponse(
  data: ModelCapabilitiesResponse,
): ModelCapsFields {
  const opts = Array.isArray(data.effort_options)
    ? data.effort_options.map(String)
    : [];
  return {
    image: Boolean(data.image),
    video: Boolean(data.video),
    thinking: Boolean(data.thinking),
    effort: String(data.effort || "medium"),
    effort_options: opts,
    image_wire: data.image_wire === "url" ? "url" : "data",
    video_wire: data.video_wire === "url" ? "url" : "data",
    max_videos:
      typeof data.max_videos === "number" && data.max_videos > 0
        ? data.max_videos
        : 1,
    max_images:
      typeof data.max_images === "number" && data.max_images > 0
        ? data.max_images
        : null,
    thinking_protocol: String(data.thinking_protocol || "none"),
  };
}

/** catalog 列表项 → 候选 draft caps（与 lookup 字段映射一致）。 */
export function capsFromCatalogItem(
  item: ModelCatalogItem,
): ModelCapsFields & { model: string } {
  const opts = Array.isArray(item.effort_options)
    ? item.effort_options.map(String)
    : [];
  return {
    model: item.id,
    image: item.image,
    video: Boolean(item.video),
    thinking: item.thinking,
    effort: pickEffortInOptions(String(item.effort || ""), opts),
    effort_options: opts,
    image_wire: item.image_wire === "url" ? "url" : "data",
    video_wire: item.video_wire === "url" ? "url" : "data",
    max_videos:
      typeof item.max_videos === "number" && item.max_videos > 0
        ? item.max_videos
        : 1,
    max_images:
      typeof item.max_images === "number" && item.max_images > 0
        ? item.max_images
        : null,
    thinking_protocol: item.thinking_protocol,
  };
}

export async function resolveModelCaps(
  model: string,
  baseUrl?: string,
): Promise<ModelCapsFields> {
  const mid = model.trim();
  if (!mid) return conservativeModelCaps();
  try {
    const res = await lookupModelCapabilities(mid, baseUrl);
    return capsFromLookupResponse(res);
  } catch {
    return conservativeModelCaps();
  }
}
