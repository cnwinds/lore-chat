import {
  SearchProviderEditor,
  type SearchProviderDraft,
} from "./SearchProviderEditor";
import {
  ImageProviderEditor,
  type ImageProviderDraft,
} from "./ImageProviderEditor";
import type { CooldownStatus } from "./settingsTypes";
import { draftChainNeedsSetup } from "./settingsAttention";
import { CandidateChainEditor } from "./CandidateChainEditor";
import { EmbedChainEditor } from "./EmbedChainEditor";
import type { EmbedCandidateDraft, ModelCandidateDraft } from "./providerPresets";

type Props = {
  publicBaseUrl: string;
  onPublicBaseUrlChange: (v: string) => void;
  chatModels: ModelCandidateDraft[];
  onChatModelsChange: (v: ModelCandidateDraft[]) => void;
  utilityModels: ModelCandidateDraft[];
  onUtilityModelsChange: (v: ModelCandidateDraft[]) => void;
  embedModels: EmbedCandidateDraft[];
  onEmbedModelsChange: (v: EmbedCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  searchProviders: SearchProviderDraft[];
  onSearchProvidersChange: (v: SearchProviderDraft[]) => void;
  searchCooldown: CooldownStatus;
  onClearSearchCooldown: (providerId: string) => void;
  imageProviders: ImageProviderDraft[];
  onImageProvidersChange: (v: ImageProviderDraft[]) => void;
  imageCooldown: CooldownStatus;
  onClearImageCooldown: (providerId: string) => void;
  saving: boolean;
  hydrated?: boolean;
};

export function ModelSettingsTab({
  publicBaseUrl,
  onPublicBaseUrlChange,
  chatModels,
  onChatModelsChange,
  utilityModels,
  onUtilityModelsChange,
  embedModels,
  onEmbedModelsChange,
  cooldown,
  onClearCooldown,
  searchProviders,
  onSearchProvidersChange,
  searchCooldown,
  onClearSearchCooldown,
  imageProviders,
  onImageProvidersChange,
  imageCooldown,
  onClearImageCooldown,
  saving,
  hydrated = true,
}: Props) {
  return (
    <>
      <CandidateChainEditor
        title="对话模型"
        candidates={chatModels}
        onChange={onChatModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(chatModels)}
        hydrated={hydrated}
      />

      <CandidateChainEditor
        title="辅助模型"
        candidates={utilityModels}
        onChange={onUtilityModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(utilityModels)}
        hydrated={hydrated}
      />

      <EmbedChainEditor
        candidates={embedModels}
        onChange={onEmbedModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(embedModels)}
        hydrated={hydrated}
      />

      <SearchProviderEditor
        providers={searchProviders}
        onChange={onSearchProvidersChange}
        cooldown={searchCooldown}
        onClearCooldown={onClearSearchCooldown}
        saving={saving}
      />

      <ImageProviderEditor
        providers={imageProviders}
        onChange={onImageProvidersChange}
        cooldown={imageCooldown}
        onClearCooldown={onClearImageCooldown}
        saving={saving}
      />

      <div className="settings-group">
        <header className="settings-group-header">
          <h3 className="settings-group-title">识图公网地址</h3>
        </header>
        <label className="settings-field">
          <span>Public Base URL</span>
          <input
            value={publicBaseUrl}
            onChange={(e) => onPublicBaseUrlChange(e.target.value)}
            disabled={saving}
            placeholder="https://your-host"
          />
        </label>
      </div>
    </>
  );
}
