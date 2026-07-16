import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  changePassword,
  downloadExport,
  getSettings,
  importKb,
  putSettings,
  reindexKb,
} from "../../api";

type Props = {
  open: boolean;
  onClose: () => void;
};

const SECRET_KEYS = [
  "openai_api_key",
  "small_api_key",
  "big_api_key",
  "embed_api_key",
  "tavily_api_key",
  "serper_api_key",
  "brave_search_api_key",
] as const;

type SecretKey = (typeof SECRET_KEYS)[number];

type SettingsTab = "model" | "search" | "agent" | "kb" | "account";

const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "模型" },
  { id: "search", label: "检索" },
  { id: "agent", label: "Agent" },
  { id: "kb", label: "知识库" },
  { id: "account", label: "账户" },
];

const SECRET_LABELS: Record<SecretKey, string> = {
  openai_api_key: "OpenAI API Key（默认）",
  small_api_key: "小模型 API Key",
  big_api_key: "大模型 API Key",
  embed_api_key: "嵌入模型 API Key",
  tavily_api_key: "Tavily API Key",
  serper_api_key: "Serper API Key",
  brave_search_api_key: "Brave Search API Key",
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

type ModelSlot = "small" | "big" | "embed";

function hasCustomEndpoint(
  baseUrl: string,
  secretKey: SecretKey,
  masked: Partial<Record<SecretKey, string>>,
  input?: string,
): boolean {
  return Boolean(baseUrl.trim() || masked[secretKey] || input?.trim());
}

type ModelConfigGroupProps = {
  title: string;
  modelName: string;
  onModelNameChange: (value: string) => void;
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  secretKey: SecretKey;
  secretInput: string;
  onSecretInputChange: (value: string) => void;
  maskedSecret?: string;
  endpointExpanded: boolean;
  onEndpointExpandedChange: (expanded: boolean) => void;
  saving: boolean;
};

function ModelConfigGroup({
  title,
  modelName,
  onModelNameChange,
  baseUrl,
  onBaseUrlChange,
  secretKey,
  secretInput,
  onSecretInputChange,
  maskedSecret,
  endpointExpanded,
  onEndpointExpandedChange,
  saving,
}: ModelConfigGroupProps) {
  const usesDefault = !hasCustomEndpoint(baseUrl, secretKey, { [secretKey]: maskedSecret }, secretInput);

  return (
    <div className="settings-group">
      <h3 className="settings-group-title">{title}</h3>
      <label className="settings-field">
        <span>模型名称</span>
        <input
          value={modelName}
          onChange={(e) => onModelNameChange(e.target.value)}
          disabled={saving}
        />
      </label>

      <button
        type="button"
        className="settings-endpoint-toggle"
        aria-expanded={endpointExpanded}
        onClick={() => onEndpointExpandedChange(!endpointExpanded)}
      >
        <span className="settings-endpoint-toggle-label">地址与密钥</span>
        <span className="settings-endpoint-toggle-meta">
          {endpointExpanded ? "收起" : usesDefault ? "使用默认" : "已自定义"}
        </span>
        <span className="settings-endpoint-toggle-icon" aria-hidden>
          {endpointExpanded ? "▲" : "▼"}
        </span>
      </button>

      {endpointExpanded ? (
        <div className="settings-endpoint-fields">
          <label className="settings-field">
            <span>Base URL</span>
            <input
              value={baseUrl}
              onChange={(e) => {
                onBaseUrlChange(e.target.value);
                if (e.target.value.trim()) onEndpointExpandedChange(true);
              }}
              disabled={saving}
              placeholder="留空则使用默认"
            />
          </label>
          <label className="settings-field">
            <span>API Key</span>
            <input
              type="password"
              autoComplete="off"
              value={secretInput}
              placeholder={maskedSecret ?? "未设置"}
              onChange={(e) => {
                onSecretInputChange(e.target.value);
                if (e.target.value.trim()) onEndpointExpandedChange(true);
              }}
              disabled={saving}
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}

export function SettingsPanel({ open, onClose }: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>("model");

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
      setActiveTab("model");
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

                    <div className="settings-group">
                      <h3 className="settings-group-title">默认</h3>
                      <p className="settings-group-hint">未单独配置的模型将使用此地址与密钥。</p>
                      <label className="settings-field">
                        <span>Base URL</span>
                        <input
                          value={openaiBaseUrl}
                          onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                          disabled={saving}
                          placeholder="https://api.openai.com/v1"
                        />
                      </label>
                      <label className="settings-field">
                        <span>API Key</span>
                        <input
                          type="password"
                          autoComplete="off"
                          value={secretInputs.openai_api_key ?? ""}
                          placeholder={maskedSecrets.openai_api_key ?? "未设置"}
                          onChange={(e) =>
                            setSecretInputs((prev) => ({ ...prev, openai_api_key: e.target.value }))
                          }
                          disabled={saving}
                        />
                      </label>
                    </div>

                    <ModelConfigGroup
                      title="小模型"
                      modelName={smallModel}
                      onModelNameChange={setSmallModel}
                      baseUrl={smallBaseUrl}
                      onBaseUrlChange={setSmallBaseUrl}
                      secretKey="small_api_key"
                      secretInput={secretInputs.small_api_key ?? ""}
                      onSecretInputChange={(value) =>
                        setSecretInputs((prev) => ({ ...prev, small_api_key: value }))
                      }
                      maskedSecret={maskedSecrets.small_api_key}
                      endpointExpanded={endpointExpanded.small}
                      onEndpointExpandedChange={(expanded) =>
                        setEndpointExpanded((prev) => ({ ...prev, small: expanded }))
                      }
                      saving={saving}
                    />

                    <ModelConfigGroup
                      title="大模型"
                      modelName={bigModel}
                      onModelNameChange={setBigModel}
                      baseUrl={bigBaseUrl}
                      onBaseUrlChange={setBigBaseUrl}
                      secretKey="big_api_key"
                      secretInput={secretInputs.big_api_key ?? ""}
                      onSecretInputChange={(value) =>
                        setSecretInputs((prev) => ({ ...prev, big_api_key: value }))
                      }
                      maskedSecret={maskedSecrets.big_api_key}
                      endpointExpanded={endpointExpanded.big}
                      onEndpointExpandedChange={(expanded) =>
                        setEndpointExpanded((prev) => ({ ...prev, big: expanded }))
                      }
                      saving={saving}
                    />

                    <ModelConfigGroup
                      title="嵌入模型"
                      modelName={embedModel}
                      onModelNameChange={setEmbedModel}
                      baseUrl={embedBaseUrl}
                      onBaseUrlChange={setEmbedBaseUrl}
                      secretKey="embed_api_key"
                      secretInput={secretInputs.embed_api_key ?? ""}
                      onSecretInputChange={(value) =>
                        setSecretInputs((prev) => ({ ...prev, embed_api_key: value }))
                      }
                      maskedSecret={maskedSecrets.embed_api_key}
                      endpointExpanded={endpointExpanded.embed}
                      onEndpointExpandedChange={(expanded) =>
                        setEndpointExpanded((prev) => ({ ...prev, embed: expanded }))
                      }
                      saving={saving}
                    />

                    <div className="settings-group">
                      <h3 className="settings-group-title">搜索密钥</h3>
                      <p className="settings-group-hint">用于联网搜索工具，可选配置。</p>
                      {SECRET_KEYS.slice(4).map((key) => (
                        <label key={key} className="settings-field">
                          <span>{SECRET_LABELS[key]}</span>
                          <input
                            type="password"
                            autoComplete="off"
                            value={secretInputs[key] ?? ""}
                            placeholder={maskedSecrets[key] ?? "未设置"}
                            onChange={(e) =>
                              setSecretInputs((prev) => ({ ...prev, [key]: e.target.value }))
                            }
                            disabled={saving}
                          />
                        </label>
                      ))}
                    </div>
                  </div>
                ) : null}

                {activeTab === "search" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-search"
                    aria-labelledby="settings-tab-search"
                  >
                    <div className="settings-group">
                      <h3 className="settings-group-title">检索参数</h3>
                      <p className="settings-group-hint">控制知识库混合检索的召回与融合策略。</p>
                      <label className="settings-field">
                        <span>向量相似度下限</span>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          value={minVectorScore}
                          onChange={(e) => setMinVectorScore(Number(e.target.value))}
                          disabled={saving}
                        />
                      </label>
                      <label className="settings-field">
                        <span>RRF K</span>
                        <input
                          type="number"
                          min="1"
                          value={rrfK}
                          onChange={(e) => setRrfK(Number(e.target.value))}
                          disabled={saving}
                        />
                      </label>
                      <label className="settings-field">
                        <span>通道候选数</span>
                        <input
                          type="number"
                          min="1"
                          value={laneCandidateK}
                          onChange={(e) => setLaneCandidateK(Number(e.target.value))}
                          disabled={saving}
                        />
                      </label>
                    </div>
                  </div>
                ) : null}

                {activeTab === "agent" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-agent"
                    aria-labelledby="settings-tab-agent"
                  >
                    <div className="settings-group">
                      <h3 className="settings-group-title">工具调用</h3>
                      <p className="settings-group-hint">控制 Agent 执行工具时的并发与次数限制。</p>
                      <label className="settings-field">
                        <span>最大工具调用次数</span>
                        <input
                          type="number"
                          min="1"
                          value={agentMaxToolCalls}
                          onChange={(e) => setAgentMaxToolCalls(Number(e.target.value))}
                          disabled={saving}
                        />
                      </label>
                      <label className="settings-field settings-field--checkbox">
                        <input
                          type="checkbox"
                          checked={agentParallelTools}
                          onChange={(e) => setAgentParallelTools(e.target.checked)}
                          disabled={saving}
                        />
                        <span>允许并行工具调用</span>
                      </label>
                      <label className="settings-field">
                        <span>最大并行数</span>
                        <input
                          type="number"
                          min="1"
                          value={agentMaxParallel}
                          onChange={(e) => setAgentMaxParallel(Number(e.target.value))}
                          disabled={!agentParallelTools || saving}
                        />
                      </label>
                    </div>
                  </div>
                ) : null}

                {activeTab === "kb" ? (
                  <div
                    className="settings-tab-panel"
                    role="tabpanel"
                    id="settings-panel-kb"
                    aria-labelledby="settings-tab-kb"
                  >
                    <div className="settings-group">
                      <h3 className="settings-group-title">存储位置</h3>
                      <label className="settings-field">
                        <span>知识库路径（只读）</span>
                        <input value={kbPath} readOnly className="settings-readonly" />
                      </label>
                    </div>

                    {backupError ? (
                      <p className="settings-panel-error">{backupError}</p>
                    ) : null}
                    {backupMsg ? (
                      <p className="settings-panel-success">{backupMsg}</p>
                    ) : null}

                    <div className="settings-group">
                      <h3 className="settings-group-title">导出</h3>
                      <p className="settings-group-hint">将当前知识库打包为 zip 文件下载到本地。</p>
                      <div className="settings-action-row">
                        <div className="settings-action-row-text">
                          <span className="settings-action-row-title">导出知识库</span>
                          <span className="settings-action-row-desc">包含文档、索引与会话数据</span>
                        </div>
                        <button
                          type="button"
                          className="settings-btn settings-btn--secondary settings-btn--compact"
                          onClick={() => void handleExport()}
                          disabled={backupBusy || saving}
                        >
                          {backupBusy ? "处理中…" : "导出"}
                        </button>
                      </div>
                    </div>

                    <div className="settings-group">
                      <h3 className="settings-group-title">导入</h3>
                      <p className="settings-group-hint">从 zip 备份包恢复知识库数据。</p>
                      <div className="settings-import-block">
                        <span className="settings-field-label">选择 zip 包</span>
                        <input
                          ref={importFileRef}
                          type="file"
                          accept=".zip,application/zip"
                          className="settings-file-input-hidden"
                          disabled={backupBusy || saving}
                          onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
                        />
                        <div className="settings-file-zone-row">
                          <button
                            type="button"
                            className={`settings-file-zone${importFile ? " settings-file-zone--selected" : ""}`}
                            disabled={backupBusy || saving}
                            onClick={() => importFileRef.current?.click()}
                          >
                            <span className="settings-file-zone-icon" aria-hidden />
                            <span className="settings-file-zone-body">
                              <span className="settings-file-zone-name">
                                {importFile ? importFile.name : "选择 zip 文件"}
                              </span>
                              <span className="settings-file-zone-hint">
                                {importFile
                                  ? `${(importFile.size / 1024 / 1024).toFixed(2)} MB · 点击可重新选择`
                                  : "点击选择知识库备份包"}
                              </span>
                            </span>
                          </button>
                          {importFile ? (
                            <button
                              type="button"
                              className="settings-file-zone-clear"
                              aria-label="清除已选文件"
                              disabled={backupBusy || saving}
                              onClick={() => {
                                setImportFile(null);
                                if (importFileRef.current) importFileRef.current.value = "";
                              }}
                            >
                              ×
                            </button>
                          ) : null}
                        </div>

                        <div className="settings-option-list" role="radiogroup" aria-label="导入模式">
                          <label
                            className={`settings-option-card${importMode === "empty_only" ? " settings-option-card--active" : ""}`}
                          >
                            <input
                              type="radio"
                              name="import-mode"
                              value="empty_only"
                              className="settings-option-card-input"
                              checked={importMode === "empty_only"}
                              onChange={() => setImportMode("empty_only")}
                              disabled={backupBusy || saving}
                            />
                            <span className="settings-option-card-title">仅空库导入</span>
                            <span className="settings-option-card-desc">知识库为空时才允许导入</span>
                          </label>
                          <label
                            className={`settings-option-card${importMode === "overwrite" ? " settings-option-card--active" : ""}`}
                          >
                            <input
                              type="radio"
                              name="import-mode"
                              value="overwrite"
                              className="settings-option-card-input"
                              checked={importMode === "overwrite"}
                              onChange={() => setImportMode("overwrite")}
                              disabled={backupBusy || saving}
                            />
                            <span className="settings-option-card-title">覆盖导入</span>
                            <span className="settings-option-card-desc">先自动备份，再覆盖现有数据</span>
                          </label>
                        </div>

                        <button
                          type="button"
                          className="settings-btn settings-btn--primary"
                          onClick={() => void handleImport()}
                          disabled={backupBusy || saving || !importFile}
                        >
                          {backupBusy ? "导入中…" : "导入知识库"}
                        </button>
                      </div>
                    </div>

                    <div className="settings-group">
                      <h3 className="settings-group-title">索引维护</h3>
                      <div className="settings-action-row">
                        <div className="settings-action-row-text">
                          <span className="settings-action-row-title">重建索引</span>
                          <span className="settings-action-row-desc">文档或会话变更后，可手动重建全文与向量索引</span>
                        </div>
                        <button
                          type="button"
                          className="settings-btn settings-btn--secondary settings-btn--compact"
                          onClick={() => void handleReindex()}
                          disabled={backupBusy || saving}
                        >
                          {backupBusy ? "重建中…" : "重建"}
                        </button>
                      </div>
                    </div>
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

              {activeTab === "account" ? (
                <div
                  className="settings-tab-panel"
                  role="tabpanel"
                  id="settings-panel-account"
                  aria-labelledby="settings-tab-account"
                >
                  <div className="settings-group">
                    <h3 className="settings-group-title">修改密码</h3>
                    <form className="settings-form" onSubmit={handleChangePassword}>
                      {pwdError ? <p className="settings-panel-error">{pwdError}</p> : null}
                      {pwdMsg ? <p className="settings-panel-success">{pwdMsg}</p> : null}
                      <label className="settings-field">
                        <span>当前密码</span>
                        <input
                          type="password"
                          autoComplete="current-password"
                          value={oldPassword}
                          onChange={(e) => setOldPassword(e.target.value)}
                          disabled={pwdSaving}
                          required
                        />
                      </label>
                      <label className="settings-field">
                        <span>新密码</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          disabled={pwdSaving}
                          required
                          minLength={8}
                        />
                      </label>
                      <label className="settings-field">
                        <span>确认新密码</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          disabled={pwdSaving}
                          required
                          minLength={8}
                        />
                      </label>
                      <button type="submit" className="settings-btn settings-btn--primary" disabled={pwdSaving}>
                        {pwdSaving ? "提交中…" : "更新密码"}
                      </button>
                    </form>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
