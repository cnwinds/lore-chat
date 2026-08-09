import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  changePassword,
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
  hasCustomEndpoint,
  ModelSettingsTab,
  SECRET_KEYS,
  type ModelSlot,
  type SecretKey,
} from "./ModelSettingsTab";
import { SearchSettingsTab } from "./SearchSettingsTab";
import { UsageSettingsTab } from "./UsageSettingsTab";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenConversation?: (conversationId: string) => void;
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

export function SettingsPanel({ open, onClose, onOpenConversation }: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>(readStoredSettingsTab);

  const [kbPath, setKbPath] = useState("");
  const [maskedSecrets, setMaskedSecrets] = useState<Partial<Record<SecretKey, string>>>({});
  const [secretInputs, setSecretInputs] = useState<Partial<Record<SecretKey, string>>>({});

  const [smallModel, setSmallModel] = useState("");
  const [bigModel, setBigModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("");
  const [smallBaseUrl, setSmallBaseUrl] = useState("");
  const [bigBaseUrl, setBigBaseUrl] = useState("");
  const [embedBaseUrl, setEmbedBaseUrl] = useState("");

  const [endpointExpanded, setEndpointExpanded] = useState<Record<ModelSlot, boolean>>({
    small: false,
    big: false,
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

      setSmallModel(str(data.small_model));
      setBigModel(str(data.big_model));
      setEmbedModel(str(data.embed_model));
      setOpenaiBaseUrl(str(data.openai_base_url));
      setSmallBaseUrl(str(data.small_base_url));
      setBigBaseUrl(str(data.big_base_url));
      setEmbedBaseUrl(str(data.embed_base_url));

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
        small: hasCustomEndpoint(str(data.small_base_url), "small_api_key", masked),
        big: hasCustomEndpoint(str(data.big_base_url), "big_api_key", masked),
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
        small_model: smallModel,
        big_model: bigModel,
        embed_model: embedModel,
        openai_base_url: openaiBaseUrl,
        small_base_url: smallBaseUrl || null,
        big_base_url: bigBaseUrl || null,
        embed_base_url: embedBaseUrl || null,
        min_vector_score: minVectorScore,
        rrf_k: rrfK,
        lane_candidate_k: laneCandidateK,
        agent_max_tool_calls: agentMaxToolCalls,
        agent_parallel_tools: agentParallelTools,
        agent_max_parallel: agentMaxParallel,
        sandbox_trust_mode: sandboxTrustMode,
        sandbox_mirror_region: sandboxMirrorRegion,
      };

      for (const key of SECRET_KEYS) {
        const input = secretInputs[key]?.trim();
        if (input) patch[key] = input;
      }

      await putSettings(patch);
      setSaveMsg("已保存并生效");
      await load();
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
          <h2 id="settings-panel-title">设置</h2>
          <button type="button" className="settings-panel-close" onClick={onClose}>
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
                    <p className="settings-tab-hint">密钥留空表示不修改；当前值已脱敏显示。</p>
                    <ModelSettingsTab
                      openaiBaseUrl={openaiBaseUrl}
                      onOpenaiBaseUrlChange={setOpenaiBaseUrl}
                      smallModel={smallModel}
                      onSmallModelChange={setSmallModel}
                      smallBaseUrl={smallBaseUrl}
                      onSmallBaseUrlChange={setSmallBaseUrl}
                      bigModel={bigModel}
                      onBigModelChange={setBigModel}
                      bigBaseUrl={bigBaseUrl}
                      onBigBaseUrlChange={setBigBaseUrl}
                      embedModel={embedModel}
                      onEmbedModelChange={setEmbedModel}
                      embedBaseUrl={embedBaseUrl}
                      onEmbedBaseUrlChange={setEmbedBaseUrl}
                      secretInputs={secretInputs}
                      setSecretInputs={setSecretInputs}
                      maskedSecrets={maskedSecrets}
                      endpointExpanded={endpointExpanded}
                      setEndpointExpanded={setEndpointExpanded}
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
