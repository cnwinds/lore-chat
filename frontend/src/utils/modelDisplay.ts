import { getSettings } from "../api";
import {
  formatVendorModelTitle,
  resolvedEmbedProviderLabel,
  resolvedLlmProviderLabel,
} from "../components/settings/providerPresets";

/** 模型 id → 厂家显示名（来自设置里的各模型链，去重后共享）。 */
let providerByModel = new Map<string, string>();
let refreshPromise: Promise<void> | null = null;

/** 拉取设置并重建映射；并发调用共享同一请求。失败静默（展示层回退裸模型名）。 */
export function applyModelSettings(s: Record<string, unknown>): void {
  const next = new Map<string, string>();
  for (const key of ["chat_models", "utility_models", "embed_models"]) {
    const list = Array.isArray(s[key]) ? s[key] : [];
    for (const c of list) {
      const model = typeof c?.model === "string" ? c.model.trim() : "";
      if (!model) continue;
      const provider =
        typeof c?.provider === "string" ? c.provider.trim() : "";
      const custom =
        typeof c?.provider_label === "string" ? c.provider_label : "";
      const resolve =
        key === "embed_models"
          ? resolvedEmbedProviderLabel
          : resolvedLlmProviderLabel;
      next.set(model, resolve(provider, custom));
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
 * 展示用模型名。信息流已记下「厂家 · 模型」时原样返回；
 * 旧记录只有裸模型名时，再按设置补厂家。兼容「- max」等推理档后缀。
 */
export function displayModelName(modelName?: string | null): string {
  const m = (modelName || "").trim();
  if (!m) return "";
  if (m.includes(" · ")) return m;
  const exact = providerByModel.get(m);
  if (exact) return formatVendorModelTitle(exact, m);
  const sep = m.indexOf(" - ");
  if (sep > 0) {
    const base = m.slice(0, sep).trim();
    const baseProvider = providerByModel.get(base);
    if (baseProvider) return formatVendorModelTitle(baseProvider, m);
  }
  return m;
}
