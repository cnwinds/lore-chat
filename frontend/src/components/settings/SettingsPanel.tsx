import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  changePassword,
  clearModelCooldown,
  clearSearchCooldown,
  downloadExport,
  getSettings,
  importKb,
  putSettings,
  reindexKb,
} from "../../api";
import { AccountSettingsTab } from "./AccountSettingsTab";
import { AgentSettingsTab } from "./AgentSettingsTab";
import { KbBackupSettingsTab } from "./KbBackupSettingsTab";
import { MemorySettingsTab } from "./MemorySettingsTab";
import {
  emptyCandidate,
  hasCustomEndpoint,
  ModelSettingsTab,
  parseCandidates,
  SECRET_KEYS,
  SEARCH_PROVIDER_OPTIONS,
  type CooldownStatus,
  type ModelCandidateDraft,
  type ModelSlot,
  type SearchProviderDraft,
  type SearchProviderId,
  type SecretKey,
} from "./ModelSettingsTab";
import { SearchSettingsTab } from "./SearchSettingsTab";
import { UsageSettingsTab } from "./UsageSettingsTab";

const SEARCH_PROVIDER_IDS = new Set(
  SEARCH_PROVIDER_OPTIONS.map((o) => o.id),
);

function parseSearchProviders(raw: unknown): SearchProviderDraft[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const out: SearchProviderDraft[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const provider = String(row.provider || "").trim().toLowerCase();
    if (!SEARCH_PROVIDER_IDS.has(provider as SearchProviderId) || seen.has(provider)) {
      continue;
    }
    seen.add(provider);
    const id = String(row.id || provider).trim() || provider;
    const rawKey = typeof row.api_key === "string" ? row.api_key.trim() : "";
    let api_key_masked: string | undefined;
    if (rawKey) {
      api_key_masked =
        rawKey.includes("***") || rawKey === "****"
          ? rawKey
          : rawKey.length <= 4
            ? "****"
            : rawKey;
    }
    out.push({
      id,
      provider: provider as SearchProviderId,
      api_key: "",
      api_key_masked,
    });
  }
  return out;
}

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenConversation?: (conversationId: string) => void;
  /** 首次进入且未配置主 API Key 时：打开设置并切到「模型」Tab，展示引导文案 */
  showLlmSetupGuide?: boolean;
  onLlmConfigured?: () => void;
};

type SettingsTab = "model" | "search" | "agent" | "kb" | "memory" | "usage" | "account";

const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "模型" },
  { id: "search", label: "检索" },
  { id: "agent", label: "Agent" },
  { id: "kb", label: "知识库" },
  { id: "memory", label: "记忆" },
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

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

function num(v: unknown, fallback: number): number {
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  const n = Number(v);
  return Number.isNaN(n) ? fallback : n;
}

function bool(v: unknown, fallback: boolean): boolean {
  if (typeof v === "boolean") return v;
  return fallback;
}

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
  onOpenConversation,
  showLlmSetupGuide = false,
  onLlmConfigured,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>(readStoredSettingsTab);

  const [kbPath, setKbPath] = useState("");
  const [maskedSecrets, setMaskedSecrets] = useState<Partial<Record<SecretKey, string>>>({});
  const [secretInputs, setSecretInputs] = useState<Partial<Record<SecretKey, string>>>({});

  const [embedModel, setEmbedModel] = useState("");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [embedBaseUrl, setEmbedBaseUrl] = useState("");
  const [chatModels, setChatModels] = useState<ModelCandidateDraft[]>([emptyCandidate()]);
  const [utilityModels, setUtilityModels] = useState<ModelCandidateDraft[]>([
    emptyCandidate(),
  ]);
  const [cooldown, setCooldown] = useState<CooldownStatus>({});
  const [searchProviders, setSearchProviders] = useState<SearchProviderDraft[]>([]);
  const [searchCooldown, setSearchCooldown] = useState<CooldownStatus>({});

  const [endpointExpanded, setEndpointExpanded] = useState<Record<ModelSlot, boolean>>({
    embed: false,
  });

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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSaveMsg(null);
    try {
      const data = await getSettings();
      setKbPath(str(data.kb_path));

      setEmbedModel(str(data.embed_model));
      setOpenaiBaseUrl(str(data.openai_base_url));
      const existingPublic = str(data.public_base_url).trim();
      if (existingPublic) {
        setPublicBaseUrl(existingPublic);
      } else {
        const auto = clientAccessOrigin();
        setPublicBaseUrl(auto);
        if (auto) {
          try {
            await putSettings({ public_base_url: auto });
            setSaveMsg("已根据当前访问地址自动填写并保存 Public Base URL");
          } catch {
            /* 仍保留表单预填，用户可手动保存 */
          }
        }
      }
      setEmbedBaseUrl(str(data.embed_base_url));
      const chat = parseCandidates(data.chat_models);
      const util = parseCandidates(data.utility_models);
      setChatModels(chat.length ? chat : [emptyCandidate()]);
      setUtilityModels(util.length ? util : [emptyCandidate()]);
      setCooldown(
        data.model_cooldown && typeof data.model_cooldown === "object"
          ? (data.model_cooldown as CooldownStatus)
          : {},
      );
      setSearchProviders(parseSearchProviders(data.search_providers));
      setSearchCooldown(
        data.search_cooldown && typeof data.search_cooldown === "object"
          ? (data.search_cooldown as CooldownStatus)
          : {},
      );

      setMinVectorScore(num(data.min_vector_score, 0.45));
      setRrfK(num(data.rrf_k, 60));
      setLaneCandidateK(num(data.lane_candidate_k, 20));

      setAgentMaxToolCalls(num(data.agent_max_tool_calls, 25));
      setAgentParallelTools(bool(data.agent_parallel_tools, true));
      setAgentMaxParallel(num(data.agent_max_parallel, 4));
      setSandboxEnabled(bool(data.sandbox_enabled, false));
      setSandboxTrustMode(bool(data.sandbox_trust_mode, true));
      setSandboxMirrorRegion(
        data.sandbox_mirror_region === "global" ? "global" : "cn",
      );

      const masked: Partial<Record<SecretKey, string>> = {};
      for (const key of SECRET_KEYS) {
        const v = data[key];
        if (typeof v === "string" && v) masked[key] = v;
      }
      setMaskedSecrets(masked);
      setSecretInputs({});
      setEndpointExpanded({
        embed: hasCustomEndpoint(str(data.embed_base_url), "embed_api_key", masked),
      });
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
      if (importFileRef.current) importFileRef.current.value = "";
    }
  }, [open, load]);

  useEffect(() => {
    if (open && showLlmSetupGuide) {
      setActiveTab("model");
    }
  }, [open, showLlmSetupGuide]);

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

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveMsg(null);
    try {
      const patch: Record<string, unknown> = {
        embed_model: embedModel,
        openai_base_url: openaiBaseUrl,
        public_base_url: publicBaseUrl.trim() || null,
        embed_base_url: endpointExpanded.embed ? embedBaseUrl.trim() || null : null,
        chat_models: chatModels.map((c) => ({
          id: c.id,
          model: c.model,
          base_url: c.use_custom_endpoint ? c.base_url.trim() || null : null,
          api_key: c.use_custom_endpoint ? c.api_key.trim() || null : null,
          use_custom_endpoint: c.use_custom_endpoint,
          image: c.image,
          thinking: c.thinking,
          effort: c.effort,
          effort_options: c.effort_options,
          image_wire: c.image_wire,
        })),
        utility_models: utilityModels.map((c) => ({
          id: c.id,
          model: c.model,
          base_url: c.use_custom_endpoint ? c.base_url.trim() || null : null,
          api_key: c.use_custom_endpoint ? c.api_key.trim() || null : null,
          use_custom_endpoint: c.use_custom_endpoint,
          image: c.image,
          thinking: c.thinking,
          effort: c.effort,
          effort_options: c.effort_options,
          image_wire: c.image_wire,
        })),
        search_providers: searchProviders.map((p) => ({
          id: p.id,
          provider: p.provider,
          api_key: p.api_key.trim() || null,
        })),
        min_vector_score: minVectorScore,
        rrf_k: rrfK,
        lane_candidate_k: laneCandidateK,
        agent_max_tool_calls: agentMaxToolCalls,
        agent_parallel_tools: agentParallelTools,
        agent_max_parallel: agentMaxParallel,
        sandbox_trust_mode: sandboxTrustMode,
        sandbox_mirror_region: sandboxMirrorRegion,
      };

      if (!endpointExpanded.embed) {
        patch.embed_api_key = null;
      }

      for (const key of SECRET_KEYS) {
        if (key === "embed_api_key" && !endpointExpanded.embed) continue;
        const input = secretInputs[key]?.trim();
        if (input) patch[key] = input;
      }

      const saved = await putSettings(patch);
      setSaveMsg("已保存并生效");
      await load();
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
            <p className="settings-panel-subtitle">模型、检索与账户</p>
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
              {tab.label}
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
                    {showLlmSetupGuide ? (
                      <p className="settings-setup-guide" role="status">
                        尚未配置 API Key。请填写下方默认 API Key（OpenAI 兼容）；也可修改 Base
                        URL 指向其它兼容网关。保存后即可开始对话。
                      </p>
                    ) : null}
                    <p className="settings-tab-hint">密钥留空表示不修改；当前值已脱敏显示。</p>
                    <ModelSettingsTab
                      openaiBaseUrl={openaiBaseUrl}
                      onOpenaiBaseUrlChange={setOpenaiBaseUrl}
                      publicBaseUrl={publicBaseUrl}
                      onPublicBaseUrlChange={setPublicBaseUrl}
                      chatModels={chatModels}
                      onChatModelsChange={setChatModels}
                      utilityModels={utilityModels}
                      onUtilityModelsChange={setUtilityModels}
                      embedModel={embedModel}
                      onEmbedModelChange={setEmbedModel}
                      embedBaseUrl={embedBaseUrl}
                      onEmbedBaseUrlChange={setEmbedBaseUrl}
                      secretInputs={secretInputs}
                      setSecretInputs={setSecretInputs}
                      maskedSecrets={maskedSecrets}
                      endpointExpanded={endpointExpanded}
                      setEndpointExpanded={setEndpointExpanded}
                      cooldown={cooldown}
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
                      saving={saving}
                    />
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

                {activeTab === "model" || activeTab === "search" || activeTab === "agent" ? (
                  <footer className="settings-form-footer">
                    <button type="submit" className="settings-btn settings-btn--primary" disabled={saving}>
                      {saving ? "保存中…" : "保存设置"}
                    </button>
                  </footer>
                ) : null}
              </form>

              {activeTab === "memory" ? (
                <MemorySettingsTab onOpenConversation={onOpenConversation} />
              ) : null}

              {activeTab === "usage" ? <UsageSettingsTab /> : null}

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
