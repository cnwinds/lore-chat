import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  changePassword,
  clearModelCooldown,
  clearSearchCooldown,
  clearImageCooldown,
  downloadExport,
  getSettings,
  importKb,
  putSettings,
  reindexKb,
} from "../../api";
import { AccountSettingsTab } from "./AccountSettingsTab";
import { AgentSettingsTab } from "./AgentSettingsTab";
import { KbBackupSettingsTab } from "./KbBackupSettingsTab";
import { ModelSettingsTab } from "./ModelSettingsTab";
import type { EmbedCandidateDraft, ModelCandidateDraft } from "./providerPresets";
import {
  type SearchProviderDraft,
} from "./SearchProviderEditor";
import {
  type ImageProviderDraft,
} from "./ImageProviderEditor";
import type { CooldownStatus } from "./settingsTypes";
import { SearchSettingsTab } from "./SearchSettingsTab";
import { UsageSettingsTab } from "./UsageSettingsTab";
import { SettingsAttentionDot } from "./SettingsAttentionDot";
import { StarterPackGuide } from "./StarterPackGuide";
import {
  applyFreeStarterPack,
  starterPackPhase,
  withStarterPackKeys,
  type StarterPackDrafts,
} from "./starterPack";
import {
  draftChainNeedsSetup,
  mergeSettingsAttention,
  searchProvidersConfigured,
} from "./settingsAttention";
import { hydrateSettingsDrafts, toSettingsPatch } from "./settingsDrafts";
import { maybeEnableComposerWebSearch } from "../../utils/webSearchPreference";
import { notifySettingsChanged } from "../../utils/settingsChangedEvent";
import type { SettingsAttention } from "../../api";

type Props = {
  open: boolean;
  onClose: () => void;
  /** 首次进入且未配置主 API Key 时：打开设置并切到「模型」Tab，展示引导文案 */
  showLlmSetupGuide?: boolean;
  onLlmConfigured?: () => void;
  /** 服务端红点；面板打开时用草稿/本地态合并后经 onLiveAttentionChange 回传 */
  attention?: SettingsAttention | null;
  /** 用量等变更后刷新服务端红点 */
  onAttentionChange?: () => void;
  /** 面板打开期间的合并红点（关闭时传 null） */
  onLiveAttentionChange?: (live: SettingsAttention | null) => void;
};

type SettingsTab = "model" | "search" | "agent" | "kb" | "usage" | "account";

const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "模型" },
  { id: "search", label: "检索" },
  { id: "agent", label: "Agent" },
  { id: "kb", label: "知识库" },
  { id: "usage", label: "用量" },
  { id: "account", label: "账户" },
];

const SETTINGS_TAB_STORAGE_KEY = "lorechat.settingsTab";
const SETTINGS_TAB_IDS = new Set<string>(SETTINGS_TABS.map((t) => t.id));

function readStoredSettingsTab(): SettingsTab {
  try {
    const stored = localStorage.getItem(SETTINGS_TAB_STORAGE_KEY);
    if (stored && SETTINGS_TAB_IDS.has(stored)) return stored as SettingsTab;
  } catch {
    /* ignore */
  }
  return "model";
}

function writeStoredSettingsTab(tab: SettingsTab) {
  try {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, tab);
  } catch {
    /* ignore */
  }
}

const EMPTY_ATTENTION: SettingsAttention = {
  any: false,
  model: { any: false, chat: false, utility: false, embed: false },
  memory: { any: false, pending_count: 0 },
  usage: { any: false, incomplete_price_count: 0 },
};

/** 浏览器当前访问源，用作 Public Base URL（无尾斜杠）。 */
function clientAccessOrigin(): string {
  if (typeof window === "undefined") return "";
  const { protocol, host } = window.location;
  if (!protocol || !host) return "";
  return `${protocol}//${host}`.replace(/\/$/, "");
}

export function SettingsPanel({
  open,
  onClose,
  showLlmSetupGuide = false,
  onLlmConfigured,
  attention = null,
  onAttentionChange,
  onLiveAttentionChange,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsReady, setSettingsReady] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>(readStoredSettingsTab);

  const [kbPath, setKbPath] = useState("");

  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [chatModels, setChatModels] = useState<ModelCandidateDraft[]>([]);
  const [utilityModels, setUtilityModels] = useState<ModelCandidateDraft[]>([]);
  const [embedModels, setEmbedModels] = useState<EmbedCandidateDraft[]>([]);
  const [cooldown, setCooldown] = useState<CooldownStatus>({});
  const [searchProviders, setSearchProviders] = useState<SearchProviderDraft[]>([]);
  const [searchCooldown, setSearchCooldown] = useState<CooldownStatus>({});
  const [imageProviders, setImageProviders] = useState<ImageProviderDraft[]>([]);
  const [imageCooldown, setImageCooldown] = useState<CooldownStatus>({});

  const [minVectorScore, setMinVectorScore] = useState(0.45);
  const [rrfK, setRrfK] = useState(60);
  const [laneCandidateK, setLaneCandidateK] = useState(20);

  const [agentMaxToolCalls, setAgentMaxToolCalls] = useState(25);
  const [agentParallelTools, setAgentParallelTools] = useState(true);
  const [agentMaxParallel, setAgentMaxParallel] = useState(4);
  const [sandboxEnabled, setSandboxEnabled] = useState(false);
  const [sandboxTrustMode, setSandboxTrustMode] = useState(true);
  const [sandboxMirrorRegion, setSandboxMirrorRegion] = useState<"cn" | "global">(
    "cn",
  );

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdSaving, setPwdSaving] = useState(false);
  const [pwdMsg, setPwdMsg] = useState<string | null>(null);
  const [pwdError, setPwdError] = useState<string | null>(null);

  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [importMode, setImportMode] = useState<"empty_only" | "overwrite">("empty_only");
  const [importFile, setImportFile] = useState<File | null>(null);
  const importFileRef = useRef<HTMLInputElement>(null);
  /** 上次从服务端载入的搜索是否已配置（用于 0→1 时打开聊天框联网搜索） */
  const searchConfiguredRef = useRef(false);
  /** 面板内本地态：覆盖服务端 usage 分区，避免未保存时不同步 */
  const [usageIncomplete, setUsageIncomplete] = useState<number | null>(null);
  const [starterDismissed, setStarterDismissed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSaveMsg(null);
    try {
      const data = await getSettings();
      const drafts = hydrateSettingsDrafts(data, {
        fallbackPublicBaseUrl: clientAccessOrigin(),
      });
      setKbPath(drafts.kbPath);
      setPublicBaseUrl(drafts.publicBaseUrl);
      if (drafts.publicBaseUrlFromFallback && drafts.publicBaseUrl) {
        try {
          await putSettings({ public_base_url: drafts.publicBaseUrl });
          setSaveMsg("已根据当前访问地址自动填写并保存 Public Base URL");
        } catch {
          /* 仍保留表单预填，用户可手动保存 */
        }
      }
      setChatModels(drafts.chatModels);
      setUtilityModels(drafts.utilityModels);
      setEmbedModels(drafts.embedModels);
      setCooldown(drafts.modelCooldown);
      setSearchProviders(drafts.searchProviders);
      searchConfiguredRef.current = searchProvidersConfigured(
        drafts.searchProviders,
      );
      setSearchCooldown(drafts.searchCooldown);
      setImageProviders(drafts.imageProviders);
      setImageCooldown(drafts.imageCooldown);
      setMinVectorScore(drafts.minVectorScore);
      setRrfK(drafts.rrfK);
      setLaneCandidateK(drafts.laneCandidateK);
      setAgentMaxToolCalls(drafts.agentMaxToolCalls);
      setAgentParallelTools(drafts.agentParallelTools);
      setAgentMaxParallel(drafts.agentMaxParallel);
      setSandboxEnabled(drafts.sandboxEnabled);
      setSandboxTrustMode(drafts.sandboxTrustMode);
      setSandboxMirrorRegion(drafts.sandboxMirrorRegion);
      setSettingsReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载设置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void load();
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwdMsg(null);
      setPwdError(null);
      setBackupMsg(null);
      setBackupError(null);
      setImportFile(null);
      setImportMode("empty_only");
      setUsageIncomplete(null);
      setStarterDismissed(false);
      if (importFileRef.current) importFileRef.current.value = "";
    } else {
      onLiveAttentionChange?.(null);
    }
  }, [open, load, onLiveAttentionChange]);

  useEffect(() => {
    if (open && showLlmSetupGuide) {
      setActiveTab("model");
    }
  }, [open, showLlmSetupGuide]);

  const starterDrafts = useMemo(
    () => ({
      chat: chatModels,
      utility: utilityModels,
      embed: embedModels,
      search: searchProviders,
    }),
    [chatModels, utilityModels, embedModels, searchProviders],
  );
  const starterPhase = starterPackPhase(starterDrafts, starterDismissed);

  useEffect(() => {
    writeStoredSettingsTab(activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

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
    if (!open) return;
    onLiveAttentionChange?.(liveAttention);
  }, [open, liveAttention, onLiveAttentionChange]);

  function applyStarterDrafts(next: StarterPackDrafts) {
    setChatModels(next.chat);
    setUtilityModels(next.utility);
    setEmbedModels(next.embed);
    setSearchProviders(next.search);
  }

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveMsg(null);
    try {
      const patch = toSettingsPatch({
        publicBaseUrl,
        chatModels,
        utilityModels,
        embedModels,
        searchProviders,
        imageProviders,
        minVectorScore,
        rrfK,
        laneCandidateK,
        agentMaxToolCalls,
        agentParallelTools,
        agentMaxParallel,
        sandboxTrustMode,
        sandboxMirrorRegion,
      });

      const wasSearchConfigured = searchConfiguredRef.current;
      const saved = await putSettings(patch);
      setSaveMsg("已保存并生效");
      notifySettingsChanged();
      maybeEnableComposerWebSearch(
        wasSearchConfigured,
        searchProvidersConfigured(searchProviders),
      );
      await load();
      onAttentionChange?.();
      if (saved.llm_api_key_configured === true) {
        onLlmConfigured?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setPwdError(null);
    setPwdMsg(null);

    if (newPassword.length < 8) {
      setPwdError("新密码至少需要 8 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwdError("两次输入的新密码不一致");
      return;
    }

    setPwdSaving(true);
    try {
      await changePassword(oldPassword, newPassword);
      setPwdMsg("密码已更新");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPwdError(err instanceof Error ? err.message : "修改密码失败");
    } finally {
      setPwdSaving(false);
    }
  }

  async function handleExport() {
    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      await downloadExport();
      setBackupMsg("知识库已导出");
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleImport() {
    if (!importFile) {
      setBackupError("请选择要导入的 zip 文件");
      return;
    }
    if (importMode === "overwrite") {
      const ok = window.confirm(
        "将先自动备份现有知识库，再覆盖。确定？",
      );
      if (!ok) return;
    }

    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const result = await importKb(importFile, importMode);
      const msg =
        result.backup_path != null
          ? `${result.message}（备份：${result.backup_path}）`
          : result.message;
      setBackupMsg(msg);
      setImportFile(null);
      await load();
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleReindex() {
    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const result = await reindexKb();
      setBackupMsg(
        `索引已重建：文档 ${result.docs_indexed}，会话 FTS ${result.conversations_fts}，会话向量 ${result.conversations_vector}`,
      );
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "重建索引失败");
    } finally {
      setBackupBusy(false);
    }
  }

  if (!open) return null;

  const tabAttentionFlags: Partial<Record<SettingsTab, boolean>> = {
    model: liveAttention.model.any,
    usage: liveAttention.usage.any,
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
              aria-selected={activeTab === tab.id}
              aria-controls={`settings-panel-${tab.id}`}
              className={`settings-tab${activeTab === tab.id ? " settings-tab--active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
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
          {loading ? (
            <p className="settings-panel-hint">加载中…</p>
          ) : (
            <>
              {error ? <p className="settings-panel-error">{error}</p> : null}
              {saveMsg ? <p className="settings-panel-success">{saveMsg}</p> : null}

              <form className="settings-form" onSubmit={handleSaveSettings}>
                {activeTab === "model" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-model"
                    aria-labelledby="settings-tab-model"
                  >
                    <StarterPackGuide
                      phase={starterPhase}
                      drafts={starterDrafts}
                      saving={saving}
                      onApply={() => {
                        void applyFreeStarterPack(starterDrafts).then(applyStarterDrafts);
                      }}
                      onDismiss={() => setStarterDismissed(true)}
                      onKeysChange={(patch) =>
                        applyStarterDrafts(withStarterPackKeys(starterDrafts, patch))
                      }
                    />
                    {starterPhase === "hidden" && showLlmSetupGuide ? (
                      <p className="settings-setup-guide" role="status">
                        在下方选择厂家，填写 Base URL 与 API
                        Key。保存后即可开始对话。
                      </p>
                    ) : null}
                    {starterPhase === "offer" ? null : (
                    <ModelSettingsTab
                      publicBaseUrl={publicBaseUrl}
                      onPublicBaseUrlChange={setPublicBaseUrl}
                      chatModels={chatModels}
                      onChatModelsChange={setChatModels}
                      utilityModels={utilityModels}
                      onUtilityModelsChange={setUtilityModels}
                      embedModels={embedModels}
                      onEmbedModelsChange={setEmbedModels}
                      cooldown={cooldown}
                      hydrated={settingsReady}
                      onClearCooldown={async (candidateId) => {
                        try {
                          const res = await clearModelCooldown({ candidate_id: candidateId });
                          if (res.model_cooldown && typeof res.model_cooldown === "object") {
                            setCooldown(res.model_cooldown as CooldownStatus);
                          }
                        } catch (err) {
                          setError(err instanceof Error ? err.message : "清除冷却失败");
                        }
                      }}
                      searchProviders={searchProviders}
                      onSearchProvidersChange={setSearchProviders}
                      searchCooldown={searchCooldown}
                      onClearSearchCooldown={async (candidateId) => {
                        try {
                          const res = await clearSearchCooldown({
                            provider_id: candidateId,
                          });
                          if (
                            res.search_cooldown &&
                            typeof res.search_cooldown === "object"
                          ) {
                            setSearchCooldown(res.search_cooldown as CooldownStatus);
                          }
                        } catch (err) {
                          setError(err instanceof Error ? err.message : "清除冷却失败");
                        }
                      }}
                      imageProviders={imageProviders}
                      onImageProvidersChange={setImageProviders}
                      imageCooldown={imageCooldown}
                      onClearImageCooldown={async (candidateId) => {
                        try {
                          const res = await clearImageCooldown({
                            provider_id: candidateId,
                          });
                          if (
                            res.image_cooldown &&
                            typeof res.image_cooldown === "object"
                          ) {
                            setImageCooldown(res.image_cooldown as CooldownStatus);
                          }
                        } catch (err) {
                          setError(err instanceof Error ? err.message : "清除冷却失败");
                        }
                      }}
                      saving={saving}
                    />
                    )}
                  </div>
                ) : null}

                {activeTab === "search" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-search"
                    aria-labelledby="settings-tab-search"
                  >
                    <SearchSettingsTab
                      minVectorScore={minVectorScore}
                      onMinVectorScoreChange={setMinVectorScore}
                      rrfK={rrfK}
                      onRrfKChange={setRrfK}
                      laneCandidateK={laneCandidateK}
                      onLaneCandidateKChange={setLaneCandidateK}
                      saving={saving}
                    />
                  </div>
                ) : null}

                {activeTab === "agent" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-agent"
                    aria-labelledby="settings-tab-agent"
                  >
                    <AgentSettingsTab
                      agentMaxToolCalls={agentMaxToolCalls}
                      onAgentMaxToolCallsChange={setAgentMaxToolCalls}
                      agentParallelTools={agentParallelTools}
                      onAgentParallelToolsChange={setAgentParallelTools}
                      agentMaxParallel={agentMaxParallel}
                      onAgentMaxParallelChange={setAgentMaxParallel}
                      sandboxEnabled={sandboxEnabled}
                      sandboxTrustMode={sandboxTrustMode}
                      onSandboxTrustModeChange={setSandboxTrustMode}
                      sandboxMirrorRegion={sandboxMirrorRegion}
                      onSandboxMirrorRegionChange={setSandboxMirrorRegion}
                      saving={saving}
                    />
                  </div>
                ) : null}

                {activeTab === "kb" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-kb"
                    aria-labelledby="settings-tab-kb"
                  >
                    <KbBackupSettingsTab
                      kbPath={kbPath}
                      backupError={backupError}
                      backupMsg={backupMsg}
                      backupBusy={backupBusy}
                      saving={saving}
                      importFile={importFile}
                      importFileRef={importFileRef}
                      importMode={importMode}
                      onImportFileChange={setImportFile}
                      onImportModeChange={setImportMode}
                      onExport={() => void handleExport()}
                      onImport={() => void handleImport()}
                      onReindex={() => void handleReindex()}
                    />
                  </div>
                ) : null}

                {(activeTab === "search" ||
                  activeTab === "agent" ||
                  (activeTab === "model" && starterPhase !== "offer")) ? (
                  <footer className="settings-form-footer">
                    <button type="submit" className="settings-btn settings-btn--primary" disabled={saving}>
                      {saving ? "保存中…" : "保存设置"}
                    </button>
                  </footer>
                ) : null}
              </form>

              {activeTab === "usage" ? (
                <UsageSettingsTab
                  onAttentionChange={onAttentionChange}
                  onIncompletePriceCountChange={setUsageIncomplete}
                />
              ) : null}

              {activeTab === "account" ? (
                <div
                  className="settings-tab-panel"
                  role="tabpanel"
                  id="settings-panel-account"
                  aria-labelledby="settings-tab-account"
                >
                  <AccountSettingsTab
                    oldPassword={oldPassword}
                    newPassword={newPassword}
                    confirmPassword={confirmPassword}
                    onOldPasswordChange={setOldPassword}
                    onNewPasswordChange={setNewPassword}
                    onConfirmPasswordChange={setConfirmPassword}
                    pwdError={pwdError}
                    pwdMsg={pwdMsg}
                    pwdSaving={pwdSaving}
                    onSubmit={handleChangePassword}
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
