import { getSettings } from "../api";
import {
  llmProviderLabel,
  type LlmProviderPresetId,
} from "../components/settings/providerPresets";

/** 模型 id → 供应商展示名（来自设置里的各模型链，去重后共享）。 */
let providerByModel = new Map<string, string>();
let refreshPromise: Promise<void> | null = null;

/** 拉取设置并重建映射；并发调用共享同一请求。失败静默（展示层回退裸模型名）。 */
export function applyModelSettings(s: Record<string, unknown>): void {
  const next = new Map<string, string>();
  for (const key of ["chat_models", "utility_models", "embed_models"]) {
    const list = Array.isArray(s[key]) ? s[key] : [];
    for (const c of list) {
      const model = typeof c?.model === "string" ? c.model.trim() : "";
      const provider =
        typeof c?.provider === "string" ? c.provider.trim() : "";
      if (!model || !provider) continue;
      next.set(model, llmProviderLabel(provider as LlmProviderPresetId));
    }
  }
  providerByModel = next;
}

export function refreshModelProviderMap(): Promise<void> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = getSettings()
    .then((s) => {
      applyModelSettings(s);
    })
    .catch(() => {
      /* 未登录 / 离线：保留空映射，展示层回退 */
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

/**
 * 展示用模型名：能解析到供应商时输出「供应商 · 模型」，
 * 否则原样返回。兼容带推理档后缀的 model_name（如 "glm-5.3-flash - max"）。
 */
export function displayModelName(modelName?: string | null): string {
  const m = (modelName || "").trim();
  if (!m) return "";
  const exact = providerByModel.get(m);
  if (exact) return `${exact} · ${m}`;
  const sep = m.indexOf(" - ");
  if (sep > 0) {
    const base = m.slice(0, sep).trim();
    const baseProvider = providerByModel.get(base);
    if (baseProvider) return `${baseProvider} · ${m}`;
  }
  return m;
}
