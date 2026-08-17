/**
 * 设置红点判定（与 backend/app/settings_attention.py 对齐）。
 * 改规则时请同步改两端测试。
 */

/** 与 candidate.PLACEHOLDER_API_KEYS / is_llm_api_key_configured 对齐 */
const PLACEHOLDER_API_KEYS = new Set(["", "sk-none", "sk-your-key"]);

export function isDraftApiKeyConfigured(
  apiKey?: string,
  apiKeyMasked?: string,
): boolean {
  const key = (apiKey || "").trim();
  if (key && !PLACEHOLDER_API_KEYS.has(key) && !key.includes("***")) {
    return true;
  }
  // 已保存脱敏：占位密钥不会以 *** 掩码回显
  const masked = (apiKeyMasked || "").trim();
  if (!masked || PLACEHOLDER_API_KEYS.has(masked)) return false;
  return masked.includes("***") || masked === "****";
}

/** 草稿态：链上至少一条具备 model + base_url + 有效 Key。 */
export function draftChainNeedsSetup(
  candidates: Array<{
    model?: string;
    base_url?: string;
    api_key?: string;
    api_key_masked?: string;
  }>,
): boolean {
  return !candidates.some((c) => {
    const model = (c.model || "").trim();
    const base = (c.base_url || "").trim();
    if (!model || !base) return false;
    return isDraftApiKeyConfigured(c.api_key, c.api_key_masked);
  });
}

/** 价目行是否缺必填单价（与后端 price_row_needs_setup 对齐）。Cache 可选。 */
export function priceRowNeedsSetup(row: {
  model: string;
  prompt_per_1m: number | null;
  completion_per_1m: number | null;
  embed_per_1m: number | null;
  kinds?: string[];
}): boolean {
  const kinds = row.kinds ?? [];
  let hasEmbed = kinds.includes("embed");
  let hasChat = kinds.some((k) => k !== "embed");
  if (!hasEmbed && !hasChat) {
    const embedLike = /embed/i.test(row.model);
    hasEmbed = embedLike;
    hasChat = !embedLike;
  }
  if (hasChat && (row.prompt_per_1m == null || row.completion_per_1m == null)) {
    return true;
  }
  if (hasEmbed && row.embed_per_1m == null) {
    return true;
  }
  return false;
}

/** 面板打开时用草稿/本地态覆盖服务端对应分区，避免红点不同步。 */
export function mergeSettingsAttention(
  server: {
    any: boolean;
    model: { any: boolean; chat: boolean; utility: boolean; embed: boolean };
    memory: { any: boolean; pending_count: number };
    usage: { any: boolean; incomplete_price_count: number };
  },
  overlay?: {
    model?: { chat: boolean; utility: boolean; embed: boolean } | null;
    memoryPending?: number | null;
    usageIncomplete?: number | null;
  } | null,
): typeof server {
  const model = overlay?.model
    ? {
        chat: overlay.model.chat,
        utility: overlay.model.utility,
        embed: overlay.model.embed,
        any:
          overlay.model.chat || overlay.model.utility || overlay.model.embed,
      }
    : server.model;
  const pending =
    overlay?.memoryPending != null
      ? overlay.memoryPending
      : server.memory.pending_count;
  const incomplete =
    overlay?.usageIncomplete != null
      ? overlay.usageIncomplete
      : server.usage.incomplete_price_count;
  const memory = {
    any: pending > 0,
    pending_count: pending,
  };
  const usage = {
    any: incomplete > 0,
    incomplete_price_count: incomplete,
  };
  return {
    any: model.any || memory.any || usage.any,
    model,
    memory,
    usage,
  };
}
