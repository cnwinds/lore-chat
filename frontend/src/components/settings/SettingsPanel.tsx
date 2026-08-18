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
import {
  emptyCandidate,
  emptyEmbedCandidate,
  embedCandidatesFromLegacy,
  ModelSettingsTab,
  maskApiKeyPlaceholder,
  parseCandidates,
  parseEmbedCandidates,
  SEARCH_PROVIDER_OPTIONS,
  IMAGE_PROVIDER_OPTIONS,
  type CooldownStatus,
  type EmbedCandidateDraft,
  type ModelCandidateDraft,
  type SearchProviderDraft,
  type SearchProviderId,
  type ImageProviderDraft,
  type ImageProviderId,
} from "./ModelSettingsTab";
import { SearchSettingsTab } from "./SearchSettingsTab";
import { UsageSettingsTab } from "./UsageSettingsTab";
import { SettingsAttentionDot } from "./SettingsAttentionDot";
import {
  draftChainNeedsSetup,
  mergeSettingsAttention,
} from "./settingsAttention";
import type { SettingsAttention } from "../../api";
import { useDemoCapability } from "../../hooks/useDemoCapability";

const SEARCH_PROVIDER_IDS = new Set(
  SEARCH_PROVIDER_OPTIONS.map((o) => o.id),
);

const IMAGE_PROVIDER_IDS = new Set(
  IMAGE_PROVIDER_OPTIONS.map((o) => o.id),
);

function parseProviderChainDrafts<T extends string>(
  raw: unknown,
  allowed: Set<string>,
  opts?: {
    /** provider：同厂家只保留一条；id：同厂家可多条、按 id 去重 */
    uniqueBy?: "provider" | "id";
    extra?: (row: Record<string, unknown>) => Record<string, string>;
  },
): Array<{
  id: string;
  provider: T;
  api_key: string;
  api_key_masked?: string;
} & Record<string, string>> {
  if (!Array.isArray(raw)) return [];
  const uniqueBy = opts?.uniqueBy ?? "provider";
  const seen = new Set<string>();
  const out: Array<{
    id: string;
    provider: T;
    api_key: string;
    api_key_masked?: string;
  } & Record<string, string>> = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const provider = String(row.provider || "").trim().toLowerCase();
    if (!allowed.has(provider)) continue;
    let id = String(row.id || "").trim();
    if (!id) {
      id = provider;
      if (uniqueBy === "id") {
        let n = 2;
        while (seen.has(id)) {
          id = `${provider}-${n}`;
          n += 1;
        }
      }
    }
    const dedupeKey = uniqueBy === "provider" ? provider : id;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    const rawKey = typeof row.api_key === "string" ? row.api_key.trim() : "";
    out.push({
      id,
      provider: provider as T,
      api_key: "",
      ...(rawKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
      ...(opts?.extra ? opts.extra(row) : {}),
    });
  }
  return out;
}

function parseSearchProviders(raw: unknown): SearchProviderDraft[] {
  return parseProviderChainDrafts<SearchProviderId>(
    raw,
    SEARCH_PROVIDER_IDS,
    { uniqueBy: "provider" },
  ) as SearchProviderDraft[];
}

/** 生图：同厂家可多条，仅按 id 去重。 */
function parseImageProviders(raw: unknown): ImageProviderDraft[] {
  return parseProviderChainDrafts<ImageProviderId>(raw, IMAGE_PROVIDER_IDS, {
    uniqueBy: "id",
    extra: (row) => ({
      base_url: typeof row.base_url === "string" ? row.base_url : "",
      model: typeof row.model === "string" ? row.model : "",
    }),
  }) as ImageProviderDraft[];
}

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
  showLlmSetupGuide = false,
  onLlmConfigured,
  attention = null,
  onAttentionChange,
  onLiveAttentionChange,
}: Props) {
  const { canWrite } = useDemoCapability();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>(readStoredSettingsTab);

  const [kbPath, setKbPath] = useState("");

  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [chatModels, setChatModels] = useState<ModelCandidateDraft[]>([emptyCandidate()]);
  const [utilityModels, setUtilityModels] = useState<ModelCandidateDraft[]>([
    emptyCandidate(),
  ]);
  const [embedModels, setEmbedModels] = useState<EmbedCandidateDraft[]>([
    emptyEmbedCandidate(),
  ]);
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
  /** 面板内本地态：覆盖服务端 usage 分区，避免未保存时不同步 */
  const [usageIncomplete, setUsageIncomplete] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSaveMsg(null);
    try {
      const data = await getSettings();
      setKbPath(str(data.kb_path));

      const existingPublic = str(data.public_base_url).trim();
      if (existingPublic) {
        setPublicBaseUrl(existingPublic);
      } else {
        const auto = clientAccessOrigin();
        setPublicBaseUrl(auto);
        if (auto && canWrite) {
          try {
            await putSettings({ public_base_url: auto });
            setSaveMsg("已根据当前访问地址自动填写并保存 Public Base URL");
          } catch {
            /* 仍保留表单预填，用户可手动保存 */
          }
        }
      }
      const chat = parseCandidates(data.chat_models);
      const util = parseCandidates(data.utility_models);
      setChatModels(chat.length ? chat : [emptyCandidate()]);
      setUtilityModels(util.length ? util : [emptyCandidate()]);
      const embeds = parseEmbedCandidates(data.embed_models);
      setEmbedModels(
        embeds.length
          ? embeds
          : embedCandidatesFromLegacy({
              embed_model: data.embed_model,
              embed_base_url: data.embed_base_url,
              embed_api_key: data.embed_api_key,
            }),
      );
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
      setImageProviders(parseImageProviders(data.image_providers));
      setImageCooldown(
        data.image_cooldown && typeof data.image_cooldown === "object"
          ? (data.image_cooldown as CooldownStatus)
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载设置失败");
    } finally {
      setLoading(false);
    }
  }, [canWrite]);

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

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveMsg(null);
    try {
      const patch: Record<string, unknown> = {
        public_base_url: publicBaseUrl.trim() || null,
        chat_models: chatModels.map((c) => ({
          id: c.id,
          model: c.model,
          provider: c.provider,
          base_url: c.base_url.trim() || null,
          api_key: c.api_key.trim() || null,
          image: c.image,
          thinking: c.thinking,
          effort: c.effort,
          effort_options: c.effort_options,
          image_wire: c.image_wire,
        })),
        utility_models: utilityModels.map((c) => ({
          id: c.id,
          model: c.model,
          provider: c.provider,
          base_url: c.base_url.trim() || null,
          api_key: c.api_key.trim() || null,
          image: c.image,
          thinking: c.thinking,
          effort: c.effort,
          effort_options: c.effort_options,
          image_wire: c.image_wire,
        })),
        embed_models: embedModels.map((c) => ({
          id: c.id,
          model: c.model,
          provider: c.provider,
          base_url: c.base_url.trim() || null,
          api_key: c.api_key.trim() || null,
          image: false,
          thinking: false,
          effort: "medium",
          effort_options: [],
          image_wire: "data",
          thinking_protocol: "none",
        })),
        search_providers: searchProviders.map((p) => ({
          id: p.id,
          provider: p.provider,
          api_key: p.api_key.trim() || null,
        })),
        image_providers: imageProviders.map((p) => ({
          id: p.id,
          provider: p.provider,
          api_key: p.api_key.trim() || null,
          base_url: p.base_url.trim() || null,
          model: p.model.trim() || null,
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

      const saved = await putSettings(patch);
      setSaveMsg("已保存并生效");
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
                    {showLlmSetupGuide ? (
                      <p className="settings-setup-guide" role="status">
                        尚未配置 API Key。请为对话/辅助模型添加候选，填写 Base URL 与 API
                        Key（OpenAI 兼容）。保存后即可开始对话。
                      </p>
                    ) : null}
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
                      onClearCooldown={
                        canWrite
                          ? async (candidateId) => {
                              try {
                                const res = await clearModelCooldown({
                                  candidate_id: candidateId,
                                });
                                if (
                                  res.model_cooldown &&
                                  typeof res.model_cooldown === "object"
                                ) {
                                  setCooldown(res.model_cooldown as CooldownStatus);
                                }
                              } catch (err) {
                                setError(
                                  err instanceof Error ? err.message : "清除冷却失败",
                                );
                              }
                            }
                          : () => undefined
                      }
                      searchProviders={searchProviders}
                      onSearchProvidersChange={setSearchProviders}
                      searchCooldown={searchCooldown}
                      onClearSearchCooldown={
                        canWrite
                          ? async (candidateId) => {
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
                                setError(
                                  err instanceof Error ? err.message : "清除冷却失败",
                                );
                              }
                            }
                          : () => undefined
                      }
                      imageProviders={imageProviders}
                      onImageProvidersChange={setImageProviders}
                      imageCooldown={imageCooldown}
                      onClearImageCooldown={
                        canWrite
                          ? async (candidateId) => {
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
                                setError(
                                  err instanceof Error ? err.message : "清除冷却失败",
                                );
                              }
                            }
                          : () => undefined
                      }
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
                    {canWrite ? (
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
                    ) : (
                      <div className="settings-group">
                        <h3 className="settings-group-title">存储位置</h3>
                        <label className="settings-field">
                          <span>知识库路径（只读）</span>
                          <input value={kbPath} readOnly className="settings-readonly" />
                        </label>
                        <p className="settings-group-hint">
                          演示环境为只读，不可导入导出或重建索引。
                        </p>
                      </div>
                    )}
                  </div>
                ) : null}

                {canWrite &&
                (activeTab === "model" || activeTab === "search" || activeTab === "agent") ? (
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

              {activeTab === "account" && canWrite ? (
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
