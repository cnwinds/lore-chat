import type { Dispatch, SetStateAction } from "react";

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

type ModelSlot = "small" | "big" | "embed";

export function hasCustomEndpoint(
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

type Props = {
  openaiBaseUrl: string;
  onOpenaiBaseUrlChange: (v: string) => void;
  smallModel: string;
  onSmallModelChange: (v: string) => void;
  smallBaseUrl: string;
  onSmallBaseUrlChange: (v: string) => void;
  bigModel: string;
  onBigModelChange: (v: string) => void;
  bigBaseUrl: string;
  onBigBaseUrlChange: (v: string) => void;
  embedModel: string;
  onEmbedModelChange: (v: string) => void;
  embedBaseUrl: string;
  onEmbedBaseUrlChange: (v: string) => void;
  secretInputs: Partial<Record<SecretKey, string>>;
  setSecretInputs: Dispatch<SetStateAction<Partial<Record<SecretKey, string>>>>;
  maskedSecrets: Partial<Record<SecretKey, string>>;
  endpointExpanded: Record<ModelSlot, boolean>;
  setEndpointExpanded: Dispatch<SetStateAction<Record<ModelSlot, boolean>>>;
  saving: boolean;
};

export type { SecretKey, ModelSlot };
export { SECRET_KEYS };

export function ModelSettingsTab({
  openaiBaseUrl,
  onOpenaiBaseUrlChange,
  smallModel,
  onSmallModelChange,
  smallBaseUrl,
  onSmallBaseUrlChange,
  bigModel,
  onBigModelChange,
  bigBaseUrl,
  onBigBaseUrlChange,
  embedModel,
  onEmbedModelChange,
  embedBaseUrl,
  onEmbedBaseUrlChange,
  secretInputs,
  setSecretInputs,
  maskedSecrets,
  endpointExpanded,
  setEndpointExpanded,
  saving,
}: Props) {
  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">默认</h3>
        <p className="settings-group-hint">未单独配置的模型将使用此地址与密钥。</p>
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
      </div>

      <ModelConfigGroup
        title="小模型"
        modelName={smallModel}
        onModelNameChange={onSmallModelChange}
        baseUrl={smallBaseUrl}
        onBaseUrlChange={onSmallBaseUrlChange}
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
        onModelNameChange={onBigModelChange}
        baseUrl={bigBaseUrl}
        onBaseUrlChange={onBigBaseUrlChange}
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
        onModelNameChange={onEmbedModelChange}
        baseUrl={embedBaseUrl}
        onBaseUrlChange={onEmbedBaseUrlChange}
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
    </>
  );
}
