import { newId } from "../../utils/id";

/** 添加对话/辅助候选时的厂家预设。 */
export type LlmProviderPresetId =
  | "openai"
  | "zhipu"
  | "bailian"
  | "deepseek"
  | "agnes"
  | "custom";

/** 嵌入模型厂家预设。 */
export type EmbedProviderPresetId = "bailian" | "siliconflow" | "custom";

/** OpenAI 兼容 Chat Completions 根地址。 */
export const LLM_PROVIDER_DEFAULT_BASE_URL: Record<
  Exclude<LlmProviderPresetId, "custom">,
  string
> = {
  openai: "https://api.openai.com/v1",
  zhipu: "https://open.bigmodel.cn/api/paas/v4",
  bailian: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  deepseek: "https://api.deepseek.com",
  agnes: "https://apihub.agnes-ai.com/v1",
};

export const EMBED_PROVIDER_DEFAULT_BASE_URL: Record<
  Exclude<EmbedProviderPresetId, "custom">,
  string
> = {
  bailian: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  siliconflow: "https://api.siliconflow.cn/v1",
};

export const LLM_PROVIDER_OPTIONS: {
  id: LlmProviderPresetId;
  label: string;
}[] = [
  { id: "openai", label: "OpenAI" },
  { id: "zhipu", label: "智谱" },
  { id: "bailian", label: "百炼 / 通义" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "agnes", label: "Agnes" },
  { id: "custom", label: "自定义" },
];

export const EMBED_PROVIDER_OPTIONS: {
  id: EmbedProviderPresetId;
  label: string;
}[] = [
  { id: "bailian", label: "百炼" },
  { id: "siliconflow", label: "硅基流动" },
  { id: "custom", label: "自定义" },
];

const LLM_PROVIDER_IDS = new Set(LLM_PROVIDER_OPTIONS.map((o) => o.id));
const EMBED_PROVIDER_IDS = new Set(EMBED_PROVIDER_OPTIONS.map((o) => o.id));

export function llmProviderLabel(id: LlmProviderPresetId): string {
  return LLM_PROVIDER_OPTIONS.find((o) => o.id === id)?.label ?? id;
}

export function embedProviderLabel(id: EmbedProviderPresetId): string {
  return EMBED_PROVIDER_OPTIONS.find((o) => o.id === id)?.label ?? id;
}

function inferPresetFromBaseUrl<T extends string>(
  baseUrl: string,
  defaults: Record<Exclude<T, "custom">, string>,
  custom: T,
): T {
  const n = baseUrl.trim().replace(/\/+$/, "").toLowerCase();
  if (!n) return custom;
  for (const [id, url] of Object.entries(defaults) as [
    Exclude<T, "custom">,
    string,
  ][]) {
    if (n === url.replace(/\/+$/, "").toLowerCase()) return id;
  }
  return custom;
}

/** 按已存 Base URL 反推厂家；对不上则为 custom。 */
export function inferProviderFromBaseUrl(baseUrl: string): LlmProviderPresetId {
  return inferPresetFromBaseUrl(baseUrl, LLM_PROVIDER_DEFAULT_BASE_URL, "custom");
}

export function inferEmbedProviderFromBaseUrl(
  baseUrl: string,
): EmbedProviderPresetId {
  return inferPresetFromBaseUrl(baseUrl, EMBED_PROVIDER_DEFAULT_BASE_URL, "custom");
}

export function parseProviderPresetId(raw: unknown): LlmProviderPresetId | null {
  const s = String(raw || "")
    .trim()
    .toLowerCase();
  if (LLM_PROVIDER_IDS.has(s as LlmProviderPresetId)) {
    return s as LlmProviderPresetId;
  }
  return null;
}

export function parseEmbedProviderPresetId(
  raw: unknown,
): EmbedProviderPresetId | null {
  const s = String(raw || "")
    .trim()
    .toLowerCase();
  if (EMBED_PROVIDER_IDS.has(s as EmbedProviderPresetId)) {
    return s as EmbedProviderPresetId;
  }
  return null;
}

export type ModelCandidateDraft = {
  id: string;
  model: string;
  base_url: string;
  api_key: string;
  /** 已保存密钥的首尾脱敏展示（作 placeholder；与检索/生图一致） */
  api_key_masked?: string;
  /** 厂家预设；非 custom 时 Base URL 只读 */
  provider: LlmProviderPresetId;
  image: boolean;
  thinking: boolean;
  effort: string;
  effort_options: string[];
  image_wire: "data" | "url";
  thinking_protocol: string;
  /** 用户手动改过能力后，onBlur 不再覆盖 */
  caps_user_edited?: boolean;
};

export type EmbedCandidateDraft = {
  id: string;
  model: string;
  base_url: string;
  api_key: string;
  api_key_masked?: string;
  provider: EmbedProviderPresetId;
};

/** 后端已脱敏则原样；否则本地补首尾掩码，避免 placeholder 露出全文。 */
export function maskApiKeyPlaceholder(rawKey: string): string {
  if (rawKey.includes("***") || rawKey === "****") return rawKey;
  if (rawKey.length <= 4) return "****";
  return `${rawKey.slice(0, 2)}***${rawKey.slice(-4)}`;
}

export function emptyCandidate(): ModelCandidateDraft {
  return {
    id: newId().slice(0, 12),
    model: "",
    base_url: "",
    api_key: "",
    provider: "custom",
    image: false,
    thinking: false,
    effort: "medium",
    effort_options: [],
    image_wire: "data",
    thinking_protocol: "none",
  };
}

/** 按厂家预设新建候选：仅预填默认 Base URL（能力等选模型后再定）。 */
export function candidateFromProvider(
  provider: LlmProviderPresetId,
): ModelCandidateDraft {
  if (provider === "custom") {
    return { ...emptyCandidate(), provider: "custom" };
  }
  return {
    ...emptyCandidate(),
    provider,
    base_url: LLM_PROVIDER_DEFAULT_BASE_URL[provider],
  };
}

export function emptyEmbedCandidate(): EmbedCandidateDraft {
  return {
    id: newId().slice(0, 12),
    model: "",
    base_url: "",
    api_key: "",
    provider: "custom",
  };
}

export function embedCandidateFromProvider(
  provider: EmbedProviderPresetId,
): EmbedCandidateDraft {
  if (provider === "custom") {
    return { ...emptyEmbedCandidate(), provider: "custom" };
  }
  return {
    ...emptyEmbedCandidate(),
    provider,
    base_url: EMBED_PROVIDER_DEFAULT_BASE_URL[provider],
  };
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

export function parseEmbedCandidates(raw: unknown): EmbedCandidateDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => {
      const base = str(x.base_url);
      const rawKey = typeof x.api_key === "string" ? x.api_key.trim() : "";
      const hadKey = Boolean(rawKey);
      const provider =
        parseEmbedProviderPresetId(x.provider) ??
        inferEmbedProviderFromBaseUrl(base);
      return {
        id: str(x.id) || newId().slice(0, 12),
        model: str(x.model),
        base_url: base,
        api_key: "",
        ...(hadKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
        provider,
      };
    });
}

/** 无 embed_models 时从旧顶层字段合成一条。 */
export function embedCandidatesFromLegacy(data: {
  embed_model?: unknown;
  embed_base_url?: unknown;
  embed_api_key?: unknown;
}): EmbedCandidateDraft[] {
  const model = str(data.embed_model);
  const base = str(data.embed_base_url);
  const rawKey =
    typeof data.embed_api_key === "string" ? data.embed_api_key.trim() : "";
  if (!model && !base && !rawKey) return [emptyEmbedCandidate()];
  return [
    {
      id: newId().slice(0, 12),
      model: model || "",
      base_url: base,
      api_key: "",
      ...(rawKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
      provider: inferEmbedProviderFromBaseUrl(base),
    },
  ];
}
