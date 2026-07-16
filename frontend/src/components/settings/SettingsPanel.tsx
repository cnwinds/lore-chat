import { useCallback, useEffect, useState, type FormEvent } from "react";
import { changePassword, getSettings, putSettings } from "../../api";

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

export function SettingsPanel({ open, onClose }: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

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

        <div className="settings-panel-body">
          {loading ? (
            <p className="settings-panel-hint">加载中…</p>
          ) : (
            <>
              {error ? <p className="settings-panel-error">{error}</p> : null}
              {saveMsg ? <p className="settings-panel-success">{saveMsg}</p> : null}

              <form className="settings-form" onSubmit={handleSaveSettings}>
                <section className="settings-section">
                  <h3>模型</h3>
                  <label className="settings-field">
                    <span>小模型</span>
                    <input
                      value={smallModel}
                      onChange={(e) => setSmallModel(e.target.value)}
                      disabled={saving}
                    />
                  </label>
                  <label className="settings-field">
                    <span>大模型</span>
                    <input
                      value={bigModel}
                      onChange={(e) => setBigModel(e.target.value)}
                      disabled={saving}
                    />
                  </label>
                  <label className="settings-field">
                    <span>嵌入模型</span>
                    <input
                      value={embedModel}
                      onChange={(e) => setEmbedModel(e.target.value)}
                      disabled={saving}
                    />
                  </label>
                  <label className="settings-field">
                    <span>默认 Base URL</span>
                    <input
                      value={openaiBaseUrl}
                      onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                      disabled={saving}
                      placeholder="https://api.openai.com/v1"
                    />
                  </label>
                  <label className="settings-field">
                    <span>小模型 Base URL</span>
                    <input
                      value={smallBaseUrl}
                      onChange={(e) => setSmallBaseUrl(e.target.value)}
                      disabled={saving}
                      placeholder="留空则使用默认"
                    />
                  </label>
                  <label className="settings-field">
                    <span>大模型 Base URL</span>
                    <input
                      value={bigBaseUrl}
                      onChange={(e) => setBigBaseUrl(e.target.value)}
                      disabled={saving}
                      placeholder="留空则使用默认"
                    />
                  </label>
                  <label className="settings-field">
                    <span>嵌入模型 Base URL</span>
                    <input
                      value={embedBaseUrl}
                      onChange={(e) => setEmbedBaseUrl(e.target.value)}
                      disabled={saving}
                      placeholder="留空则使用默认"
                    />
                  </label>
                </section>

                <section className="settings-section">
                  <h3>API 密钥</h3>
                  <p className="settings-section-hint">留空表示不修改；当前值已脱敏显示。</p>
                  {SECRET_KEYS.slice(0, 4).map((key) => (
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
                  <button
                    type="button"
                    className="settings-advanced-toggle"
                    onClick={() => setAdvancedOpen((v) => !v)}
                  >
                    {advancedOpen ? "收起搜索密钥 ▲" : "搜索密钥 ▼"}
                  </button>
                  {advancedOpen
                    ? SECRET_KEYS.slice(4).map((key) => (
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
                      ))
                    : null}
                </section>

                <section className="settings-section">
                  <h3>检索</h3>
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
                </section>

                <section className="settings-section">
                  <h3>Agent</h3>
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
                </section>

                <section className="settings-section">
                  <h3>知识库</h3>
                  <label className="settings-field">
                    <span>知识库路径（只读）</span>
                    <input value={kbPath} readOnly className="settings-readonly" />
                  </label>
                </section>

                <footer className="settings-form-footer">
                  <button type="submit" className="settings-save-btn" disabled={saving}>
                    {saving ? "保存中…" : "保存设置"}
                  </button>
                </footer>
              </form>

              <section className="settings-section settings-section--password">
                <h3>修改密码</h3>
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
                  <button type="submit" className="settings-save-btn" disabled={pwdSaving}>
                    {pwdSaving ? "提交中…" : "更新密码"}
                  </button>
                </form>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
