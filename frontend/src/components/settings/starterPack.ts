import { newId } from "../../utils/id";
import { inferCapsFromModel } from "./ModelSettingsTab";
import { draftChainNeedsSetup, isDraftApiKeyConfigured } from "./settingsAttention";
import {
  candidateFromProvider,
  embedCandidateFromProvider,
  type EmbedCandidateDraft,
  type ModelCandidateDraft,
} from "./providerPresets";
import type { SearchProviderDraft } from "./SearchProviderEditor";

export const STARTER_AGNES_MODEL = "agnes-2.5-flash";
export const STARTER_EMBED_MODEL = "baai/bge-m3";
export const STARTER_DEEPSEEK_CHAT_MODEL = "deepseek-v4-flash-0731";

export type StarterPackDrafts = {
  chat: ModelCandidateDraft[];
  utility: ModelCandidateDraft[];
  embed: EmbedCandidateDraft[];
  search: SearchProviderDraft[];
};

export type StarterPackPhase = "offer" | "collecting" | "hidden";

export type StarterPackKeys = {
  agnes: string;
  siliconflow: string;
  tavily: string;
};

function sameModel(a: string | undefined, b: string): boolean {
  return (a || "").trim().toLowerCase() === b.toLowerCase();
}

export function isAgnesFlashCandidate(
  c: ModelCandidateDraft | undefined,
): boolean {
  return Boolean(c && c.provider === "agnes" && sameModel(c.model, STARTER_AGNES_MODEL));
}

export function isStarterEmbedCandidate(
  c: EmbedCandidateDraft | undefined,
): boolean {
  return Boolean(
    c && c.provider === "siliconflow" && sameModel(c.model, STARTER_EMBED_MODEL),
  );
}

export function hasTavily(search: SearchProviderDraft[]): boolean {
  return search.some((p) => p.provider === "tavily");
}

function agnesFlashCandidate(): ModelCandidateDraft {
  const base = candidateFromProvider("agnes");
  return {
    ...base,
    model: STARTER_AGNES_MODEL,
    ...inferCapsFromModel(STARTER_AGNES_MODEL, base.base_url),
  };
}

function siliconflowEmbedCandidate(): EmbedCandidateDraft {
  return {
    ...embedCandidateFromProvider("siliconflow"),
    model: STARTER_EMBED_MODEL,
  };
}

function emptyTavily(): SearchProviderDraft {
  return { id: newId().slice(0, 12), provider: "tavily", api_key: "" };
}

function ensureTavily(search: SearchProviderDraft[]): SearchProviderDraft[] {
  if (hasTavily(search)) return search;
  return [...search, emptyTavily()];
}

/** 无模型名、地址、有效 Key 的链视为空，含未填的残留候选。 */
export function starterChainVacant(
  candidates: Array<{
    model?: string;
    base_url?: string;
    api_key?: string;
    api_key_masked?: string;
  }>,
): boolean {
  return !candidates.some((c) => {
    if ((c.model || "").trim() || (c.base_url || "").trim()) return true;
    return isDraftApiKeyConfigured(c.api_key, c.api_key_masked);
  });
}

/** 套用免费起步套餐：对话/辅助 Agnes Flash，嵌入 bge-m3，搜索 Tavily。 */
export function applyFreeStarterPack(current: StarterPackDrafts): StarterPackDrafts {
  return {
    chat: [agnesFlashCandidate()],
    utility: [agnesFlashCandidate()],
    embed: [siliconflowEmbedCandidate()],
    search: ensureTavily(current.search),
  };
}

export function isStarterPackShape(drafts: StarterPackDrafts): boolean {
  return (
    isAgnesFlashCandidate(drafts.chat[0]) &&
    isAgnesFlashCandidate(drafts.utility[0]) &&
    isStarterEmbedCandidate(drafts.embed[0]) &&
    hasTavily(drafts.search)
  );
}

export function starterPackCanSave(drafts: StarterPackDrafts): boolean {
  return (
    !draftChainNeedsSetup(drafts.chat) && !draftChainNeedsSetup(drafts.utility)
  );
}

/** 草稿里还有未落盘的明文 Key 时，引导应停在收 Key，避免保存前卡片消失。 */
export function starterPackHasPlaintextKeys(drafts: StarterPackDrafts): boolean {
  if (drafts.chat[0]?.api_key.trim()) return true;
  if (drafts.utility[0]?.api_key.trim()) return true;
  if (drafts.embed[0]?.api_key.trim()) return true;
  return drafts.search.some((p) => p.provider === "tavily" && Boolean(p.api_key.trim()));
}

export function starterPackPhase(
  drafts: StarterPackDrafts,
  dismissed: boolean,
): StarterPackPhase {
  if (dismissed) return "hidden";
  if (
    isStarterPackShape(drafts) &&
    (!starterPackCanSave(drafts) || starterPackHasPlaintextKeys(drafts))
  ) {
    return "collecting";
  }
  if (
    starterChainVacant(drafts.chat) &&
    starterChainVacant(drafts.utility) &&
    starterChainVacant(drafts.embed)
  ) {
    return "offer";
  }
  return "hidden";
}

export function readStarterPackKeys(drafts: StarterPackDrafts): StarterPackKeys {
  const agnesRow = isAgnesFlashCandidate(drafts.chat[0])
    ? drafts.chat[0]
    : drafts.utility.find(isAgnesFlashCandidate);
  const tavily = drafts.search.find((p) => p.provider === "tavily");
  return {
    agnes: agnesRow?.api_key ?? "",
    siliconflow: drafts.embed[0]?.api_key ?? "",
    tavily: tavily?.api_key ?? "",
  };
}

export function withStarterPackKeys(
  drafts: StarterPackDrafts,
  patch: Partial<StarterPackKeys>,
): StarterPackDrafts {
  const next: StarterPackDrafts = {
    chat: drafts.chat.map((c) => ({ ...c })),
    utility: drafts.utility.map((c) => ({ ...c })),
    embed: drafts.embed.map((c) => ({ ...c })),
    search: drafts.search.map((p) => ({ ...p })),
  };
  if (patch.agnes !== undefined) {
    next.chat = next.chat.map((c) =>
      isAgnesFlashCandidate(c) ? { ...c, api_key: patch.agnes! } : c,
    );
    next.utility = next.utility.map((c) =>
      isAgnesFlashCandidate(c) ? { ...c, api_key: patch.agnes! } : c,
    );
  }
  if (patch.siliconflow !== undefined) {
    next.embed = next.embed.map((c) =>
      isStarterEmbedCandidate(c) ? { ...c, api_key: patch.siliconflow! } : c,
    );
  }
  if (patch.tavily !== undefined) {
    next.search = next.search.map((p) =>
      p.provider === "tavily" ? { ...p, api_key: patch.tavily! } : p,
    );
  }
  return next;
}
