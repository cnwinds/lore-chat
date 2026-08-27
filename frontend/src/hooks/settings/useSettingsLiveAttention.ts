import { useEffect, useMemo } from "react";
import type { SettingsAttention } from "../../api";
import type { EmbedCandidateDraft, ModelCandidateDraft } from "../../components/settings/providerPresets";
import {
  draftChainNeedsSetup,
  mergeSettingsAttention,
} from "../../components/settings/settingsAttention";

const EMPTY_ATTENTION: SettingsAttention = {
  any: false,
  model: { any: false, chat: false, utility: false, embed: false },
  memory: { any: false, pending_count: 0 },
  usage: { any: false, incomplete_price_count: 0 },
};

type Options = {
  open: boolean;
  loading: boolean;
  attention: SettingsAttention | null | undefined;
  chatModels: ModelCandidateDraft[];
  utilityModels: ModelCandidateDraft[];
  embedModels: EmbedCandidateDraft[];
  usageIncomplete: number | null;
  onLiveAttentionChange?: (live: SettingsAttention | null) => void;
};

/** 合并服务端红点与面板内草稿态，并回传 App 侧栏。 */
export function useSettingsLiveAttention({
  open,
  loading,
  attention,
  chatModels,
  utilityModels,
  embedModels,
  usageIncomplete,
  onLiveAttentionChange,
}: Options) {
  const liveAttention = useMemo(() => {
    const server = attention ?? EMPTY_ATTENTION;
    const modelOverlay =
      !open || loading
        ? null
        : {
            chat: draftChainNeedsSetup(chatModels),
            utility: draftChainNeedsSetup(utilityModels),
            embed: draftChainNeedsSetup(embedModels),
          };
    return mergeSettingsAttention(server, {
      model: modelOverlay,
      usageIncomplete: open ? usageIncomplete : null,
    });
  }, [
    open,
    loading,
    chatModels,
    utilityModels,
    embedModels,
    attention,
    usageIncomplete,
  ]);

  useEffect(() => {
    if (!open) {
      onLiveAttentionChange?.(null);
      return;
    }
    onLiveAttentionChange?.(liveAttention);
  }, [open, liveAttention, onLiveAttentionChange]);

  return liveAttention;
}
