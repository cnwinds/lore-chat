import type { Dispatch, SetStateAction } from "react";

const SECRET_KEYS = [
  "openai_api_key",
  "embed_api_key",
  "tavily_api_key",
  "serper_api_key",
  "brave_search_api_key",
] as const;

type SecretKey = (typeof SECRET_KEYS)[number];

const SECRET_LABELS: Record<SecretKey, string> = {
  openai_api_key: "OpenAI API Key（默认）",
  embed_api_key: "嵌入模型 API Key",
  tavily_api_key: "Tavily API Key",
  serper_api_key: "Serper API Key",
  brave_search_api_key: "Brave Search API Key",
};

export type ModelCandidateDraft = {
  id: string;
  model: string;
  base_url: string;
  api_key: string;
  image: boolean;
  thinking: boolean;
  effort: "low" | "medium" | "high";
  image_wire: "data" | "url";
  thinking_protocol: string;
  /** 用户手动改过能力后，onBlur 不再覆盖 */
  caps_user_edited?: boolean;
};

type ModelSlot = "embed";

export type CooldownStatus = Record<
  string,
  {
    available?: boolean;
    disabled?: boolean;
    cooldown_remaining_sec?: number;
    last_error?: string | null;
  }
>;

export function hasCustomEndpoint(
  baseUrl: string,
  secretKey: SecretKey,
  masked: Partial<Record<SecretKey, string>>,
  input?: string,
): boolean {
  return Boolean(baseUrl.trim() || masked[secretKey] || input?.trim());
}

export function emptyCandidate(): ModelCandidateDraft {
  return {
    id: crypto.randomUUID().slice(0, 12),
    model: "",
    base_url: "",
    api_key: "",
    image: false,
    thinking: false,
    effort: "medium",
    image_wire: "data",
    thinking_protocol: "none",
  };
}

export function parseCandidates(raw: unknown): ModelCandidateDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => ({
      id: str(x.id) || crypto.randomUUID().slice(0, 12),
      model: str(x.model),
      base_url: str(x.base_url),
      api_key: "",
      image: Boolean(x.image),
      thinking: Boolean(x.thinking),
      effort: (x.effort === "low" || x.effort === "high" ? x.effort : "medium") as
        | "low"
        | "medium"
        | "high",
      image_wire: x.image_wire === "url" ? "url" : "data",
      thinking_protocol: str(x.thinking_protocol) || "none",
    }));
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

type ChainEditorProps = {
  title: string;
  hint: string;
  candidates: ModelCandidateDraft[];
  onChange: (next: ModelCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
};

function ChainEditor({
  title,
  hint,
  candidates,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
}: ChainEditorProps) {
  function updateAt(i: number, patch: Partial<ModelCandidateDraft>) {
    onChange(candidates.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= candidates.length) return;
    const next = [...candidates];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }

  return (
    <div className="settings-group">
      <h3 className="settings-group-title">{title}</h3>
      <p className="settings-group-hint">{hint} 列表顺序即优先级。</p>
      {candidates.map((c, i) => {
        const st = cooldown[c.id];
        return (
          <div key={c.id} className="settings-model-candidate">
            <div className="settings-model-candidate-head">
              <strong>#{i + 1}</strong>
              <button type="button" disabled={saving || i === 0} onClick={() => move(i, -1)}>
                上移
              </button>
              <button
                type="button"
                disabled={saving || i === candidates.length - 1}
                onClick={() => move(i, 1)}
              >
                下移
              </button>
              <button
                type="button"
                disabled={saving || candidates.length <= 1}
                onClick={() => onChange(candidates.filter((_, idx) => idx !== i))}
              >
                删除
              </button>
            </div>
            <label className="settings-field">
              <span>模型名称</span>
              <input
                value={c.model}
                onChange={(e) => updateAt(i, { model: e.target.value })}
                onBlur={(e) => {
                  if (c.caps_user_edited) return;
                  const name = e.target.value.trim().toLowerCase();
                  if (name.startsWith("agnes-")) {
                    updateAt(i, {
                      image: true,
                      thinking: true,
                      image_wire: "url",
                      thinking_protocol: "agnes",
                    });
                  } else if (name.startsWith("deepseek-")) {
                    updateAt(i, {
                      image: false,
                      thinking: true,
                      image_wire: "data",
                      thinking_protocol: "deepseek",
                    });
                  } else if (name.startsWith("qwen")) {
                    updateAt(i, {
                      image: true,
                      thinking: true,
                      image_wire: "data",
                      thinking_protocol: "qwen",
                    });
                  }
                }}
                disabled={saving}
              />
            </label>
            <label className="settings-field">
              <span>Base URL</span>
              <input
                value={c.base_url}
                onChange={(e) => updateAt(i, { base_url: e.target.value })}
                disabled={saving}
                placeholder="留空则使用默认"
              />
            </label>
            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                autoComplete="off"
                value={c.api_key}
                onChange={(e) => updateAt(i, { api_key: e.target.value })}
                disabled={saving}
                placeholder="留空则使用默认 / 保持原密钥"
              />
            </label>
            <div className="settings-model-caps">
              <label>
                <input
                  type="checkbox"
                  checked={c.image}
                  onChange={(e) =>
                    updateAt(i, { image: e.target.checked, caps_user_edited: true })
                  }
                  disabled={saving}
                />
                识图
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={c.thinking}
                  onChange={(e) =>
                    updateAt(i, { thinking: e.target.checked, caps_user_edited: true })
                  }
                  disabled={saving}
                />
                思考
              </label>
              <label>
                强度
                <select
                  value={c.effort}
                  onChange={(e) =>
                    updateAt(i, {
                      effort: e.target.value as ModelCandidateDraft["effort"],
                      caps_user_edited: true,
                    })
                  }
                  disabled={saving || !c.thinking}
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
              <label>
                识图传输
                <select
                  value={c.image_wire}
                  onChange={(e) =>
                    updateAt(i, {
                      image_wire: e.target.value as ModelCandidateDraft["image_wire"],
                      caps_user_edited: true,
                    })
                  }
                  disabled={saving || !c.image}
                >
                  <option value="data">data</option>
                  <option value="url">url</option>
                </select>
              </label>
              <label>
                思考协议
                <select
                  value={c.thinking_protocol}
                  onChange={(e) =>
                    updateAt(i, {
                      thinking_protocol: e.target.value,
                      caps_user_edited: true,
                    })
                  }
                  disabled={saving || !c.thinking}
                >
                  <option value="none">none</option>
                  <option value="agnes">agnes</option>
                  <option value="deepseek">deepseek</option>
                  <option value="qwen">qwen</option>
                  <option value="openai_kwargs">openai_kwargs</option>
                </select>
              </label>
            </div>
            {st && (!st.available || st.disabled) ? (
              <p className="settings-group-hint">
                {st.disabled
                  ? `已禁用${st.last_error ? `：${st.last_error}` : ""}`
                  : `冷却中 ${st.cooldown_remaining_sec ?? 0}s`}
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => onClearCooldown(c.id)}
                  style={{ marginLeft: 8 }}
                >
                  立即重试
                </button>
              </p>
            ) : null}
          </div>
        );
      })}
      <button
        type="button"
        disabled={saving}
        onClick={() => onChange([...candidates, emptyCandidate()])}
      >
        添加候选
      </button>
    </div>
  );
}

type Props = {
  openaiBaseUrl: string;
  onOpenaiBaseUrlChange: (v: string) => void;
  publicBaseUrl: string;
  onPublicBaseUrlChange: (v: string) => void;
  chatModels: ModelCandidateDraft[];
  onChatModelsChange: (v: ModelCandidateDraft[]) => void;
  utilityModels: ModelCandidateDraft[];
  onUtilityModelsChange: (v: ModelCandidateDraft[]) => void;
  embedModel: string;
  onEmbedModelChange: (v: string) => void;
  embedBaseUrl: string;
  onEmbedBaseUrlChange: (v: string) => void;
  secretInputs: Partial<Record<SecretKey, string>>;
  setSecretInputs: Dispatch<SetStateAction<Partial<Record<SecretKey, string>>>>;
  maskedSecrets: Partial<Record<SecretKey, string>>;
  endpointExpanded: Record<ModelSlot, boolean>;
  setEndpointExpanded: Dispatch<SetStateAction<Record<ModelSlot, boolean>>>;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
};

export type { SecretKey, ModelSlot };
export { SECRET_KEYS };

export function ModelSettingsTab({
  openaiBaseUrl,
  onOpenaiBaseUrlChange,
  publicBaseUrl,
  onPublicBaseUrlChange,
  chatModels,
  onChatModelsChange,
  utilityModels,
  onUtilityModelsChange,
  embedModel,
  onEmbedModelChange,
  embedBaseUrl,
  onEmbedBaseUrlChange,
  secretInputs,
  setSecretInputs,
  maskedSecrets,
  endpointExpanded,
  setEndpointExpanded,
  cooldown,
  onClearCooldown,
  saving,
}: Props) {
  const embedUsesDefault = !hasCustomEndpoint(
    embedBaseUrl,
    "embed_api_key",
    maskedSecrets,
    secretInputs.embed_api_key,
  );

  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">默认</h3>
        <p className="settings-group-hint">未单独配置的候选将使用此地址与密钥。</p>
        <label className="settings-field">
          <span>Base URL</span>
          <input
            value={openaiBaseUrl}
            onChange={(e) => onOpenaiBaseUrlChange(e.target.value)}
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
        <label className="settings-field">
          <span>Public Base URL</span>
          <input
            value={publicBaseUrl}
            onChange={(e) => onPublicBaseUrlChange(e.target.value)}
            disabled={saving}
            placeholder="https://your-host（Agnes 等 url 识图必填）"
          />
        </label>
        <p className="settings-group-hint">
          供签名附件 URL 使用；未填写时 url 识图候选在有图轮次会被跳过。
        </p>
      </div>

      <ChainEditor
        title="对话模型（chat）"
        hint="用户可见对话与 Agent 工具循环。"
        candidates={chatModels}
        onChange={onChatModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
      />

      <ChainEditor
        title="辅助模型（utility）"
        hint="记忆抽取等后台任务；与对话链互不借用。"
        candidates={utilityModels}
        onChange={onUtilityModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
      />

      <div className="settings-group">
        <h3 className="settings-group-title">嵌入模型</h3>
        <label className="settings-field">
          <span>模型名称</span>
          <input
            value={embedModel}
            onChange={(e) => onEmbedModelChange(e.target.value)}
            disabled={saving}
          />
        </label>
        <button
          type="button"
          className="settings-endpoint-toggle"
          aria-expanded={endpointExpanded.embed}
          onClick={() =>
            setEndpointExpanded((prev) => ({ ...prev, embed: !prev.embed }))
          }
        >
          <span className="settings-endpoint-toggle-label">地址与密钥</span>
          <span className="settings-endpoint-toggle-meta">
            {endpointExpanded.embed ? "收起" : embedUsesDefault ? "使用默认" : "已自定义"}
          </span>
        </button>
        {endpointExpanded.embed ? (
          <div className="settings-endpoint-fields">
            <label className="settings-field">
              <span>Base URL</span>
              <input
                value={embedBaseUrl}
                onChange={(e) => onEmbedBaseUrlChange(e.target.value)}
                disabled={saving}
                placeholder="留空则使用默认"
              />
            </label>
            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                autoComplete="off"
                value={secretInputs.embed_api_key ?? ""}
                placeholder={maskedSecrets.embed_api_key ?? "未设置"}
                onChange={(e) =>
                  setSecretInputs((prev) => ({ ...prev, embed_api_key: e.target.value }))
                }
                disabled={saving}
              />
            </label>
          </div>
        ) : null}
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">搜索密钥</h3>
        <p className="settings-group-hint">用于联网搜索工具，可选配置。</p>
        {SECRET_KEYS.slice(2).map((key) => (
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
    </>
  );
}
