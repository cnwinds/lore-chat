import { parseCandidates } from "./modelChainDrafts";
import {
  maskApiKeyPlaceholder,
  parseEmbedCandidates,
  type EmbedCandidateDraft,
  type ModelCandidateDraft,
} from "./providerPresets";
import {
  SEARCH_PROVIDER_OPTIONS,
  type SearchProviderDraft,
  type SearchProviderId,
} from "./SearchProviderEditor";
import {
  IMAGE_PROVIDER_OPTIONS,
  type ImageProviderDraft,
  type ImageProviderId,
} from "./ImageProviderEditor";
import type { CooldownStatus } from "./settingsTypes";

const SEARCH_PROVIDER_IDS = new Set(
  SEARCH_PROVIDER_OPTIONS.map((o) => o.id),
);

const IMAGE_PROVIDER_IDS = new Set(
  IMAGE_PROVIDER_OPTIONS.map((o) => o.id),
);

export type SettingsFormDrafts = {
  kbPath: string;
  publicBaseUrl: string;
  /** hydrate 用了 fallback；Panel 可选择 auto-put */
  publicBaseUrlFromFallback: boolean;
  chatModels: ModelCandidateDraft[];
  utilityModels: ModelCandidateDraft[];
  embedModels: EmbedCandidateDraft[];
  modelCooldown: CooldownStatus;
  searchProviders: SearchProviderDraft[];
  searchCooldown: CooldownStatus;
  imageProviders: ImageProviderDraft[];
  imageCooldown: CooldownStatus;
  minVectorScore: number;
  rrfK: number;
  laneCandidateK: number;
  webSearchDefaultK: number;
  agentMaxToolCalls: number;
  agentParallelTools: boolean;
  agentMaxParallel: number;
  sandboxEnabled: boolean;
  sandboxTrustMode: boolean;
  sandboxMirrorRegion: "cn" | "global";
};

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

export function clampWebSearchDefaultK(n: number): number {
  if (!Number.isFinite(n)) return 5;
  return Math.min(20, Math.max(1, Math.round(n)));
}

function num(v: unknown, fallback: number): number {
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  const n = Number(v);
  return Number.isNaN(n) ? fallback : n;
}

function bool(v: unknown, fallback: boolean): boolean {
  if (typeof v === "boolean") return v;
  return fallback;
}

function asCooldown(raw: unknown): CooldownStatus {
  return raw && typeof raw === "object" ? (raw as CooldownStatus) : {};
}

function parseProviderChainDrafts<T extends string>(
  raw: unknown,
  allowed: Set<string>,
  opts?: {
    uniqueBy?: "provider" | "id";
    extra?: (row: Record<string, unknown>) => Record<string, string>;
  },
): Array<{
  id: string;
  provider: T;
  api_key: string;
  api_key_masked?: string;
} & Record<string, string>> {
  if (!Array.isArray(raw)) return [];
  const uniqueBy = opts?.uniqueBy ?? "provider";
  const seen = new Set<string>();
  const out: Array<{
    id: string;
    provider: T;
    api_key: string;
    api_key_masked?: string;
  } & Record<string, string>> = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const provider = String(row.provider || "").trim().toLowerCase();
    if (!allowed.has(provider)) continue;
    let id = String(row.id || "").trim();
    if (!id) {
      id = provider;
      if (uniqueBy === "id") {
        let n = 2;
        while (seen.has(id)) {
          id = `${provider}-${n}`;
          n += 1;
        }
      }
    }
    const dedupeKey = uniqueBy === "provider" ? provider : id;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const rawKey = typeof row.api_key === "string" ? row.api_key.trim() : "";
    out.push({
      id,
      provider: provider as T,
      api_key: "",
      ...(rawKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
      ...(opts?.extra ? opts.extra(row) : {}),
    });
  }
  return out;
}

export function parseSearchProviders(raw: unknown): SearchProviderDraft[] {
  return parseProviderChainDrafts<SearchProviderId>(raw, SEARCH_PROVIDER_IDS, {
    uniqueBy: "provider",
  }) as SearchProviderDraft[];
}

/** 生图：同厂家可多条，仅按 id 去重。 */
export function parseImageProviders(raw: unknown): ImageProviderDraft[] {
  return parseProviderChainDrafts<ImageProviderId>(raw, IMAGE_PROVIDER_IDS, {
    uniqueBy: "id",
    extra: (row) => ({
      base_url: typeof row.base_url === "string" ? row.base_url : "",
      model: typeof row.model === "string" ? row.model : "",
    }),
  }) as ImageProviderDraft[];
}

export function draftCandidateHasContent(c: {
  model?: string;
  base_url?: string;
  api_key?: string;
  api_key_masked?: string;
}): boolean {
  return Boolean(
    (c.model || "").trim() ||
      (c.base_url || "").trim() ||
      (c.api_key || "").trim() ||
      (c.api_key_masked || "").trim(),
  );
}

export function hydrateSettingsDrafts(
  data: Record<string, unknown>,
  opts?: { fallbackPublicBaseUrl?: string },
): SettingsFormDrafts {
  const existingPublic = str(data.public_base_url).trim();
  const fallback = (opts?.fallbackPublicBaseUrl || "").trim();
  const publicBaseUrlFromFallback = !existingPublic && Boolean(fallback);
  return {
    kbPath: str(data.kb_path),
    publicBaseUrl: existingPublic || fallback,
    publicBaseUrlFromFallback,
    chatModels: parseCandidates(data.chat_models),
    utilityModels: parseCandidates(data.utility_models),
    embedModels: parseEmbedCandidates(data.embed_models),
    modelCooldown: asCooldown(data.model_cooldown),
    searchProviders: parseSearchProviders(data.search_providers),
    searchCooldown: asCooldown(data.search_cooldown),
    imageProviders: parseImageProviders(data.image_providers),
    imageCooldown: asCooldown(data.image_cooldown),
    minVectorScore: num(data.min_vector_score, 0.45),
    rrfK: num(data.rrf_k, 60),
    laneCandidateK: num(data.lane_candidate_k, 20),
    webSearchDefaultK: clampWebSearchDefaultK(num(data.web_search_default_k, 5)),
    agentMaxToolCalls: num(data.agent_max_tool_calls, 25),
    agentParallelTools: bool(data.agent_parallel_tools, true),
    agentMaxParallel: num(data.agent_max_parallel, 4),
    sandboxEnabled: bool(data.sandbox_enabled, false),
    sandboxTrustMode: bool(data.sandbox_trust_mode, true),
    sandboxMirrorRegion:
      data.sandbox_mirror_region === "global" ? "global" : "cn",
  };
}

export function toSettingsPatch(drafts: {
  publicBaseUrl: string;
  chatModels: ModelCandidateDraft[];
  utilityModels: ModelCandidateDraft[];
  embedModels: EmbedCandidateDraft[];
  searchProviders: SearchProviderDraft[];
  imageProviders: ImageProviderDraft[];
  minVectorScore: number;
  rrfK: number;
  laneCandidateK: number;
  webSearchDefaultK: number;
  agentMaxToolCalls: number;
  agentParallelTools: boolean;
  agentMaxParallel: number;
  sandboxTrustMode: boolean;
  sandboxMirrorRegion: "cn" | "global";
}): Record<string, unknown> {
  return {
    public_base_url: drafts.publicBaseUrl.trim() || null,
    chat_models: drafts.chatModels.filter(draftCandidateHasContent).map((c) => ({
      id: c.id,
      model: c.model,
      provider: c.provider,
      base_url: c.base_url.trim() || null,
      api_key: c.api_key.trim() || null,
      image: c.image,
      video: c.video,
      thinking: c.thinking,
      effort: c.effort,
      effort_options: c.effort_options,
      image_wire: c.image_wire,
      video_wire: c.video_wire,
      max_videos: c.max_videos,
      max_images: c.max_images,
    })),
    utility_models: drafts.utilityModels
      .filter(draftCandidateHasContent)
      .map((c) => ({
        id: c.id,
        model: c.model,
        provider: c.provider,
        base_url: c.base_url.trim() || null,
        api_key: c.api_key.trim() || null,
        image: c.image,
        video: c.video,
        thinking: c.thinking,
        effort: c.effort,
        effort_options: c.effort_options,
        image_wire: c.image_wire,
        video_wire: c.video_wire,
        max_videos: c.max_videos,
        max_images: c.max_images,
      })),
    embed_models: drafts.embedModels.filter(draftCandidateHasContent).map((c) => ({
      id: c.id,
      model: c.model,
      provider: c.provider,
      base_url: c.base_url.trim() || null,
      api_key: c.api_key.trim() || null,
      image: false,
      thinking: false,
      effort: "medium",
      effort_options: [],
      image_wire: "data",
      thinking_protocol: "none",
    })),
    search_providers: drafts.searchProviders.map((p) => ({
      id: p.id,
      provider: p.provider,
      api_key: p.api_key.trim() || null,
    })),
    image_providers: drafts.imageProviders.map((p) => ({
      id: p.id,
      provider: p.provider,
      api_key: p.api_key.trim() || null,
      base_url: p.base_url.trim() || null,
      model: p.model.trim() || null,
    })),
    min_vector_score: drafts.minVectorScore,
    rrf_k: drafts.rrfK,
    lane_candidate_k: drafts.laneCandidateK,
    web_search_default_k: clampWebSearchDefaultK(drafts.webSearchDefaultK),
    agent_max_tool_calls: drafts.agentMaxToolCalls,
    agent_parallel_tools: drafts.agentParallelTools,
    agent_max_parallel: drafts.agentMaxParallel,
    sandbox_trust_mode: drafts.sandboxTrustMode,
    sandbox_mirror_region: drafts.sandboxMirrorRegion,
  };
}
