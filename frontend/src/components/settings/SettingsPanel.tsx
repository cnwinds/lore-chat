import type { SettingsAttention } from "../../api";
import { AccountSettingsTab } from "./AccountSettingsTab";
import { AgentSettingsTab } from "./AgentSettingsTab";
import { KbBackupSettingsTab } from "./KbBackupSettingsTab";
import { ModelSettingsTab } from "./ModelSettingsTab";
import { ShareSettingsTab } from "./ShareSettingsTab";
import { SearchSettingsTab } from "./SearchSettingsTab";
import { UsageSettingsTab } from "./UsageSettingsTab";
import { SettingsAttentionDot } from "./SettingsAttentionDot";
import { StarterPackGuide } from "./StarterPackGuide";
import {
  applyFreeStarterPack,
  withStarterPackKeys,
} from "./starterPack";
import {
  SETTINGS_TABS,
  type SettingsTab,
} from "../../hooks/settings/settingsTabStorage";
import { useSettingsSession } from "../../hooks/settings/useSettingsSession";

export type { SettingsTab };

type Props = {
  open: boolean;
  onClose: () => void;
  navigateToTab?: SettingsTab | null;
  onNavigateToTabHandled?: () => void;
  showLlmSetupGuide?: boolean;
  onLlmConfigured?: () => void;
  attention?: SettingsAttention | null;
  onAttentionChange?: () => void;
  onLiveAttentionChange?: (live: SettingsAttention | null) => void;
};

export function SettingsPanel({
  open,
  onClose,
  navigateToTab = null,
  onNavigateToTabHandled,
  showLlmSetupGuide = false,
  onLlmConfigured,
  attention = null,
  onAttentionChange,
  onLiveAttentionChange,
}: Props) {
  const session = useSettingsSession({
    open,
    onClose,
    navigateToTab,
    onNavigateToTabHandled,
    showLlmSetupGuide,
    onLlmConfigured,
    attention,
    onAttentionChange,
    onLiveAttentionChange,
  });

  if (!open) return null;

  const tabAttentionFlags: Partial<Record<SettingsTab, boolean>> = {
    model: session.liveAttention.model.any,
    usage: session.liveAttention.usage.any,
  };

  return (
    <div className="settings-panel-backdrop" onClick={onClose}>
      <aside
        className="settings-panel"
        onClick={(ev) => ev.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-panel-title"
      >
        <header className="settings-panel-header">
          <div className="settings-panel-heading">
            <h2 id="settings-panel-title">设置</h2>
          </div>
          <button
            type="button"
            className="settings-panel-close"
            onClick={onClose}
            aria-label="关闭设置"
          >
            ×
          </button>
        </header>

        <nav className="settings-tabs" role="tablist" aria-label="设置分类">
          {SETTINGS_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`settings-tab-${tab.id}`}
              aria-selected={session.activeTab === tab.id}
              aria-controls={`settings-panel-${tab.id}`}
              className={`settings-tab${session.activeTab === tab.id ? " settings-tab--active" : ""}`}
              onClick={() => session.setActiveTab(tab.id)}
            >
              <span className="settings-tab-label">
                {tab.label}
                {tabAttentionFlags[tab.id] ? (
                  <SettingsAttentionDot />
                ) : null}
              </span>
            </button>
          ))}
        </nav>

        <div className="settings-panel-body">
          {session.loading ? (
            <p className="settings-panel-hint">加载中…</p>
          ) : (
            <>
              {session.error ? (
                <p className="settings-panel-error">{session.error}</p>
              ) : null}
              {session.saveMsg ? (
                <p className="settings-panel-success">{session.saveMsg}</p>
              ) : null}

              <form className="settings-form" onSubmit={session.handleSaveSettings}>
                {session.activeTab === "model" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-model"
                    aria-labelledby="settings-tab-model"
                  >
                    <StarterPackGuide
                      phase={session.starterPhase}
                      drafts={session.starterDrafts}
                      saving={session.saving}
                      onApply={() => {
                        void applyFreeStarterPack(session.starterDrafts).then(
                          session.applyStarterDrafts,
                        );
                      }}
                      onDismiss={() => session.setStarterDismissed(true)}
                      onKeysChange={(patch) =>
                        session.applyStarterDrafts(
                          withStarterPackKeys(session.starterDrafts, patch),
                        )
                      }
                    />
                    {session.starterPhase === "hidden" && showLlmSetupGuide ? (
                      <p className="settings-setup-guide" role="status">
                        在下方选择厂家，填写 Base URL 与 API
                        Key。保存后即可开始对话。
                      </p>
                    ) : null}
                    {session.starterPhase === "offer" ? null : (
                      <ModelSettingsTab
                        publicBaseUrl={session.publicBaseUrl}
                        onPublicBaseUrlChange={session.setPublicBaseUrl}
                        chatModels={session.chatModels}
                        onChatModelsChange={session.setChatModels}
                        utilityModels={session.utilityModels}
                        onUtilityModelsChange={session.setUtilityModels}
                        embedModels={session.embedModels}
                        onEmbedModelsChange={session.setEmbedModels}
                        cooldown={session.cooldown}
                        hydrated={session.settingsReady}
                        onClearCooldown={(id) => void session.clearModelCooldownFor(id)}
                        searchProviders={session.searchProviders}
                        onSearchProvidersChange={session.setSearchProviders}
                        searchCooldown={session.searchCooldown}
                        onClearSearchCooldown={(id) =>
                          void session.clearSearchCooldownFor(id)
                        }
                        imageProviders={session.imageProviders}
                        onImageProvidersChange={session.setImageProviders}
                        imageCooldown={session.imageCooldown}
                        onClearImageCooldown={(id) =>
                          void session.clearImageCooldownFor(id)
                        }
                        saving={session.saving}
                      />
                    )}
                  </div>
                ) : null}

                {session.activeTab === "search" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-search"
                    aria-labelledby="settings-tab-search"
                  >
                    <SearchSettingsTab
                      minVectorScore={session.minVectorScore}
                      onMinVectorScoreChange={session.setMinVectorScore}
                      rrfK={session.rrfK}
                      onRrfKChange={session.setRrfK}
                      laneCandidateK={session.laneCandidateK}
                      onLaneCandidateKChange={session.setLaneCandidateK}
                      webSearchDefaultK={session.webSearchDefaultK}
                      onWebSearchDefaultKChange={session.setWebSearchDefaultK}
                      saving={session.saving}
                    />
                  </div>
                ) : null}

                {session.activeTab === "agent" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-agent"
                    aria-labelledby="settings-tab-agent"
                  >
                    <AgentSettingsTab
                      agentMaxToolCalls={session.agentMaxToolCalls}
                      onAgentMaxToolCallsChange={session.setAgentMaxToolCalls}
                      agentParallelTools={session.agentParallelTools}
                      onAgentParallelToolsChange={session.setAgentParallelTools}
                      agentMaxParallel={session.agentMaxParallel}
                      onAgentMaxParallelChange={session.setAgentMaxParallel}
                      sandboxEnabled={session.sandboxEnabled}
                      sandboxTrustMode={session.sandboxTrustMode}
                      onSandboxTrustModeChange={session.setSandboxTrustMode}
                      sandboxMirrorRegion={session.sandboxMirrorRegion}
                      onSandboxMirrorRegionChange={session.setSandboxMirrorRegion}
                      saving={session.saving}
                    />
                  </div>
                ) : null}

                {session.activeTab === "kb" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-kb"
                    aria-labelledby="settings-tab-kb"
                  >
                    <KbBackupSettingsTab
                      kbPath={session.kbPath}
                      backupError={session.backupError}
                      backupMsg={session.backupMsg}
                      backupBusy={session.backupBusy}
                      saving={session.saving}
                      importFile={session.importFile}
                      importFileRef={session.importFileRef}
                      importMode={session.importMode}
                      onImportFileChange={session.setImportFile}
                      onImportModeChange={session.setImportMode}
                      onExport={() => void session.handleExport()}
                      onImport={() => void session.handleImport()}
                      onReindex={() => void session.handleReindex()}
                    />
                  </div>
                ) : null}

                {(session.activeTab === "search" ||
                  session.activeTab === "agent" ||
                  (session.activeTab === "model" &&
                    session.starterPhase !== "offer")) ? (
                  <footer className="settings-form-footer">
                    <button
                      type="submit"
                      className="settings-btn settings-btn--primary"
                      disabled={session.saving}
                    >
                      {session.saving ? "保存中…" : "保存设置"}
                    </button>
                  </footer>
                ) : null}
              </form>

              {session.activeTab === "usage" ? (
                <UsageSettingsTab
                  onAttentionChange={onAttentionChange}
                  onIncompletePriceCountChange={session.setUsageIncomplete}
                />
              ) : null}

              {session.activeTab === "share" ? (
                <div
                  className="settings-tab-panel"
                  role="tabpanel"
                  id="settings-panel-share"
                  aria-labelledby="settings-tab-share"
                >
                  <ShareSettingsTab />
                </div>
              ) : null}

              {session.activeTab === "account" ? (
                <div
                  className="settings-tab-panel"
                  role="tabpanel"
                  id="settings-panel-account"
                  aria-labelledby="settings-tab-account"
                >
                  <AccountSettingsTab
                    oldPassword={session.oldPassword}
                    newPassword={session.newPassword}
                    confirmPassword={session.confirmPassword}
                    onOldPasswordChange={session.setOldPassword}
                    onNewPasswordChange={session.setNewPassword}
                    onConfirmPasswordChange={session.setConfirmPassword}
                    pwdError={session.pwdError}
                    pwdMsg={session.pwdMsg}
                    pwdSaving={session.pwdSaving}
                    onSubmit={session.handleChangePassword}
                  />
                </div>
              ) : null}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
