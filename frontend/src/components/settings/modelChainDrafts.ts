import { newId } from "../../utils/id";
import {
  inferProviderFromBaseUrl,
  maskApiKeyPlaceholder,
  parseProviderPresetId,
  type ModelCandidateDraft,
} from "./providerPresets";

export function pickEffortInOptions(effort: string, opts: string[]): string {
  if (!opts.length) return effort || "medium";
  if (opts.includes(effort)) return effort;
  if (opts.includes("medium")) return "medium";
  return opts[0];
}

export function parseCandidates(raw: unknown): ModelCandidateDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => {
      const model = str(x.model);
      const protocol = str(x.thinking_protocol) || "none";
      // 空数组 = 目录声明无强度档；缺字段不再本地前缀臆造
      const opts = Array.isArray(x.effort_options)
        ? x.effort_options.map(String)
        : [];
      const effort = pickEffortInOptions(str(x.effort), opts);
      const base = str(x.base_url);
      const rawKey = typeof x.api_key === "string" ? x.api_key.trim() : "";
      const hadKey = Boolean(rawKey);
      const provider =
        parseProviderPresetId(x.provider) ?? inferProviderFromBaseUrl(base);
      return {
        id: str(x.id) || newId().slice(0, 12),
        model,
        base_url: base,
        api_key: "",
        ...(hadKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
        provider,
        image: Boolean(x.image),
        thinking: Boolean(x.thinking),
        effort,
        effort_options: opts,
        image_wire: x.image_wire === "url" ? "url" : "data",
        thinking_protocol: protocol,
      };
    });
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}
