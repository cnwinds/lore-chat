import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { searchModelCatalog, type ModelCatalogItem } from "../../api";
import { newId } from "../../utils/id";

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
  effort: string;
  effort_options: string[];
  image_wire: "data" | "url";
  thinking_protocol: string;
  /** 是否使用独立 Base URL / API Key；关闭则走默认 */
  use_custom_endpoint: boolean;
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

/** 与后端 effort.supported_efforts 对齐 */
export function supportedEfforts(model: string, protocol?: string): string[] {
  const mid = model.trim().toLowerCase();
  const proto = (protocol || "").trim().toLowerCase();
  if (proto === "deepseek" || proto === "qwen" || proto === "agnes") {
    return ["low", "medium", "high"];
  }
  if (mid.startsWith("gpt-5.2")) return ["none", "low", "medium", "high", "xhigh"];
  if (mid.startsWith("gpt-5.1")) return ["none", "low", "medium", "high"];
  if (mid.startsWith("gpt-5")) return ["minimal", "low", "medium", "high"];
  if (mid.startsWith("o1") || mid.startsWith("o3") || mid.startsWith("o4")) {
    return ["low", "medium", "high"];
  }
  if (proto === "openai_kwargs") {
    return ["none", "minimal", "low", "medium", "high", "xhigh"];
  }
  return ["low", "medium", "high"];
}

export function defaultEffort(model: string, protocol?: string): string {
  const opts = supportedEfforts(model, protocol);
  const mid = model.trim().toLowerCase();
  if (mid.startsWith("gpt-5.2") || mid.startsWith("gpt-5.1")) {
    return opts.includes("none") ? "none" : opts[0];
  }
  return opts.includes("medium") ? "medium" : opts[Math.floor(opts.length / 2)];
}

export function coerceEffort(value: string | undefined, model: string, protocol?: string): string {
  const opts = supportedEfforts(model, protocol);
  if (value && opts.includes(value)) return value;
  return defaultEffort(model, protocol);
}

export function emptyCandidate(): ModelCandidateDraft {
  return {
    id: newId().slice(0, 12),
    model: "",
    base_url: "",
    api_key: "",
    image: false,
    thinking: false,
    effort: "medium",
    effort_options: ["low", "medium", "high"],
    image_wire: "data",
    thinking_protocol: "none",
    use_custom_endpoint: false,
  };
}

export function parseCandidates(raw: unknown): ModelCandidateDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => {
      const model = str(x.model);
      const protocol = str(x.thinking_protocol) || "none";
      const opts =
        Array.isArray(x.effort_options) && x.effort_options.length
          ? x.effort_options.map(String)
          : supportedEfforts(model, protocol);
      const base = str(x.base_url);
      const hadKey = typeof x.api_key === "string" && Boolean(x.api_key.trim());
      return {
        id: str(x.id) || newId().slice(0, 12),
        model,
        base_url: base,
        api_key: "",
        image: Boolean(x.image),
        thinking: Boolean(x.thinking),
        effort: coerceEffort(str(x.effort) || undefined, model, protocol),
        effort_options: opts,
        image_wire: x.image_wire === "url" ? "url" : "data",
        thinking_protocol: protocol,
        use_custom_endpoint: Boolean(base.trim() || hadKey),
      };
    });
}

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

/** 与后端 catalog 前缀启发对齐：思考协议自适应，无需手选。 */
export function inferThinkingProtocol(
  model: string,
  baseUrl?: string,
): ModelCandidateDraft["thinking_protocol"] {
  const mid = model.trim().toLowerCase();
  if (mid.startsWith("agnes-") || (baseUrl || "").toLowerCase().includes("agnes-ai.com")) {
    return "agnes";
  }
  if (mid.startsWith("deepseek-")) return "deepseek";
  if (mid.startsWith("qwen")) return "qwen";
  if (
    mid.startsWith("o1") ||
    mid.startsWith("o3") ||
    mid.startsWith("o4") ||
    mid.startsWith("gpt-5")
  ) {
    return "openai_kwargs";
  }
  return "none";
}

function inferCapsFromModel(
  model: string,
  baseUrl?: string,
): Pick<
  ModelCandidateDraft,
  | "image"
  | "thinking"
  | "image_wire"
  | "thinking_protocol"
  | "effort"
  | "effort_options"
> {
  const mid = model.trim().toLowerCase();
  const protocol = inferThinkingProtocol(model, baseUrl);
  const opts = supportedEfforts(model, protocol);
  const effort = defaultEffort(model, protocol);
  if (mid.startsWith("agnes-") || (baseUrl || "").toLowerCase().includes("agnes-ai.com")) {
    return {
      image: true,
      thinking: true,
      image_wire: "url",
      thinking_protocol: protocol,
      effort,
      effort_options: opts,
    };
  }
  if (mid.startsWith("deepseek-")) {
    return {
      image: false,
      thinking: true,
      image_wire: "data",
      thinking_protocol: protocol,
      effort,
      effort_options: opts,
    };
  }
  if (mid.startsWith("qwen")) {
    return {
      image: true,
      thinking: true,
      image_wire: "data",
      thinking_protocol: protocol,
      effort,
      effort_options: opts,
    };
  }
  if (
    mid.startsWith("o1") ||
    mid.startsWith("o3") ||
    mid.startsWith("o4") ||
    mid.startsWith("gpt-5")
  ) {
    return {
      image: true,
      thinking: true,
      image_wire: "data",
      thinking_protocol: protocol,
      effort,
      effort_options: opts,
    };
  }
  return {
    image: false,
    thinking: false,
    image_wire: "data",
    thinking_protocol: "none",
    effort: "medium",
    effort_options: opts,
  };
}

function capsFromCatalogItem(
  item: ModelCatalogItem,
): Pick<
  ModelCandidateDraft,
  | "model"
  | "image"
  | "thinking"
  | "effort"
  | "effort_options"
  | "image_wire"
  | "thinking_protocol"
> {
  const opts =
    item.effort_options?.length > 0
      ? item.effort_options
      : supportedEfforts(item.id, item.thinking_protocol);
  return {
    model: item.id,
    image: item.image,
    thinking: item.thinking,
    effort: coerceEffort(item.effort, item.id, item.thinking_protocol),
    effort_options: opts,
    image_wire: item.image_wire,
    thinking_protocol: item.thinking_protocol,
  };
}

type ModelNameFieldProps = {
  value: string;
  disabled: boolean;
  baseUrl?: string;
  capsUserEdited?: boolean;
  /** false：仅改模型名（嵌入模型）；默认 true 会带上能力 */
  applyCapabilities?: boolean;
  /** 目录筛选：llm 排除嵌入；embedding 仅嵌入 */
  catalogKind?: "all" | "llm" | "embedding";
  label?: string;
  onPatch: (patch: Partial<ModelCandidateDraft>) => void;
};

function ModelNameField({
  value,
  disabled,
  baseUrl = "",
  capsUserEdited,
  applyCapabilities = true,
  catalogKind = "llm",
  label = "模型名称",
  onPatch,
}: ModelNameFieldProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(value);
  const [items, setItems] = useState<ModelCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    setQ(value);
  }, [value]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!open) return;
    const my = ++seq.current;
    const handle = window.setTimeout(() => {
      setLoading(true);
      void searchModelCatalog(q, { limit: 30, kind: catalogKind })
        .then((res) => {
          if (seq.current !== my) return;
          setItems(res.items || []);
          const st = res.status || {};
          if (st.error && !(st.count && st.count > 0)) {
            setHint("目录暂不可用，可手填模型名");
          } else if (st.source === "empty") {
            setHint("目录尚未就绪，稍后刷新或手填");
          } else {
            setHint(
              st.count
                ? `models.dev · ${st.count} 条${st.stale ? "（待刷新）" : ""}`
                : null,
            );
          }
        })
        .catch(() => {
          if (seq.current !== my) return;
          setItems([]);
          setHint("目录查询失败，可手填模型名");
        })
        .finally(() => {
          if (seq.current === my) setLoading(false);
        });
    }, 220);
    return () => window.clearTimeout(handle);
  }, [open, q, catalogKind]);

  function applyTyped(name: string) {
    if (!applyCapabilities) {
      onPatch({ model: name });
      return;
    }
    const hit = items.find((it) => it.id.toLowerCase() === name.toLowerCase());
    if (hit && !capsUserEdited) {
      onPatch({ ...capsFromCatalogItem(hit), caps_user_edited: false });
      return;
    }
    const inferred = inferCapsFromModel(name, baseUrl);
    if (capsUserEdited) {
      onPatch({
        model: name,
        thinking_protocol: inferred.thinking_protocol,
        effort_options: inferred.effort_options,
      });
    } else {
      // 无目录精确命中时不瞎改识图/思考；留给点选或后端 enrich（保存缺省字段时）
      onPatch({
        model: name,
        thinking_protocol: inferred.thinking_protocol,
        effort_options: inferred.effort_options,
        effort: coerceEffort(inferred.effort, name, inferred.thinking_protocol),
      });
    }
  }

  return (
    <div className="settings-model-picker" ref={wrapRef}>
      <label className="settings-field">
        <span>{label}</span>
        <input
          value={q}
          disabled={disabled}
          placeholder="搜索或输入模型名"
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            onPatch({ model: e.target.value });
          }}
          onBlur={() => {
            window.setTimeout(() => applyTyped(q.trim()), 120);
          }}
        />
      </label>
      {open ? (
        <div className="settings-model-picker-menu" role="listbox">
          <div className="settings-model-picker-meta">
            {loading ? "搜索中…" : hint || "输入关键字过滤"}
          </div>
          {items.length === 0 && !loading ? (
            <div className="settings-model-picker-empty">无匹配，可直接使用上方手填名</div>
          ) : (
            items.map((it) => (
              <button
                key={`${it.provider}/${it.id}`}
                type="button"
                className="settings-model-picker-item"
                role="option"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (applyCapabilities) {
                    const fromCat = capsFromCatalogItem(it);
                    if (capsUserEdited) {
                      onPatch({
                        model: fromCat.model,
                        thinking_protocol: fromCat.thinking_protocol,
                        effort_options: fromCat.effort_options,
                        effort: coerceEffort(
                          fromCat.effort,
                          fromCat.model,
                          fromCat.thinking_protocol,
                        ),
                      });
                    } else {
                      onPatch({ ...fromCat, caps_user_edited: false });
                    }
                  } else {
                    onPatch({ model: it.id });
                  }
                  setQ(it.id);
                  setOpen(false);
                }}
              >
                <span className="settings-model-picker-id">{it.id}</span>
                <span className="settings-model-picker-sub">
                  {it.provider}
                  {it.name && it.name !== it.id ? ` · ${it.name}` : ""}
                </span>
                <span className="settings-model-picker-tags">
                  {it.embedding ? <em>嵌入</em> : null}
                  {it.image ? <em>识图</em> : null}
                  {it.thinking ? <em>思考</em> : null}
                  {it.image_wire === "url" ? <em>url</em> : null}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
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
    <section className="settings-group settings-chain">
      <header className="settings-group-header">
        <h3 className="settings-group-title">{title}</h3>
        <p className="settings-group-hint">{hint} 列表顺序即优先级。</p>
      </header>
      <div className="settings-chain-list">
        {candidates.map((c, i) => {
          const st = cooldown[c.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          return (
            <article
              key={c.id}
              className={[
                "settings-model-candidate",
                i === 0 ? "settings-model-candidate--primary" : "",
                disabled ? "settings-model-candidate--disabled" : "",
                cooling ? "settings-model-candidate--cooling" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <div className="settings-model-candidate-head">
                <span
                  className={`settings-priority-badge${i === 0 ? " settings-priority-badge--primary" : ""}`}
                  title={i === 0 ? "最高优先级" : `优先级 ${i + 1}`}
                >
                  {i + 1}
                </span>
                <div className="settings-model-candidate-main">
                  <ModelNameField
                    value={c.model}
                    disabled={saving}
                    baseUrl={c.base_url}
                    capsUserEdited={c.caps_user_edited}
                    catalogKind="llm"
                    onPatch={(patch) => updateAt(i, patch)}
                  />
                </div>
                <div className="settings-model-candidate-actions">
                  <button
                    type="button"
                    className={`settings-endpoint-toggle${c.use_custom_endpoint ? " settings-endpoint-toggle--on" : ""}`}
                    aria-pressed={c.use_custom_endpoint}
                    title={
                      c.use_custom_endpoint
                        ? "独立端点已开：使用本行 URL / Key"
                        : "独立端点已关：使用默认 URL / Key"
                    }
                    disabled={saving}
                    onClick={() => {
                      const on = !c.use_custom_endpoint;
                      updateAt(
                        i,
                        on
                          ? { use_custom_endpoint: true }
                          : { use_custom_endpoint: false, base_url: "", api_key: "" },
                      );
                    }}
                  >
                    独立
                  </button>
                  <button
                    type="button"
                    className="settings-icon-btn"
                    disabled={saving || i === 0}
                    onClick={() => move(i, -1)}
                    aria-label="上移"
                    title="上移"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="settings-icon-btn"
                    disabled={saving || i === candidates.length - 1}
                    onClick={() => move(i, 1)}
                    aria-label="下移"
                    title="下移"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="settings-icon-btn settings-icon-btn--danger"
                    disabled={saving || candidates.length <= 1}
                    onClick={() => onChange(candidates.filter((_, idx) => idx !== i))}
                    aria-label="删除"
                    title="删除"
                  >
                    ×
                  </button>
                </div>
              </div>

              <div className="settings-model-toolbar">
                <div className="settings-model-caps">
                  <label className={`settings-cap-chip${c.image ? " settings-cap-chip--on" : ""}`}>
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
                  <label
                    className={`settings-cap-chip${c.thinking ? " settings-cap-chip--on" : ""}`}
                  >
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
                  <label className="settings-cap-select">
                    <span>强度</span>
                    <select
                      value={
                        (c.effort_options || []).includes(c.effort)
                          ? c.effort
                          : coerceEffort(c.effort, c.model, c.thinking_protocol)
                      }
                      onChange={(e) => updateAt(i, { effort: e.target.value })}
                      disabled={saving || !c.thinking}
                    >
                      {(c.effort_options?.length
                        ? c.effort_options
                        : supportedEfforts(c.model, c.thinking_protocol)
                      ).map((lv) => (
                        <option key={lv} value={lv}>
                          {lv}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="settings-cap-select">
                    <span>识图传输</span>
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
                </div>
              </div>

              {c.use_custom_endpoint ? (
                <div className="settings-field-row">
                  <label className="settings-field">
                    <span>Base URL</span>
                    <input
                      value={c.base_url}
                      onChange={(e) => updateAt(i, { base_url: e.target.value })}
                      onBlur={(e) => {
                        const inferred = inferCapsFromModel(c.model, e.target.value);
                        updateAt(i, {
                          thinking_protocol: inferred.thinking_protocol,
                          effort_options: inferred.effort_options,
                        });
                      }}
                      disabled={saving}
                      placeholder="https://…"
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
                      placeholder="留空保持原密钥"
                    />
                  </label>
                </div>
              ) : null}

              {st && (!st.available || st.disabled) ? (
                <div
                  className={`settings-health-bar${disabled ? " settings-health-bar--danger" : " settings-health-bar--warn"}`}
                >
                  <span className="settings-health-dot" aria-hidden />
                  <span className="settings-health-text">
                    {disabled
                      ? `已禁用${st.last_error ? ` · ${st.last_error}` : ""}`
                      : `冷却中 · ${st.cooldown_remaining_sec ?? 0}s`}
                  </span>
                  <button
                    type="button"
                    className="settings-btn settings-btn--compact settings-btn--secondary"
                    disabled={saving}
                    onClick={() => onClearCooldown(c.id)}
                  >
                    立即重试
                  </button>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      <button
        type="button"
        className="settings-btn settings-btn--secondary settings-chain-add"
        disabled={saving}
        onClick={() => onChange([...candidates, emptyCandidate()])}
      >
        + 添加候选
      </button>
    </section>
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
  return (
    <>
      <div className="settings-group">
        <header className="settings-group-header">
          <h3 className="settings-group-title">默认</h3>
          <p className="settings-group-hint">未单独配置的候选将使用此地址与密钥。</p>
        </header>
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
          供签名附件 URL 使用。首次为空时会按当前浏览器访问地址自动填写并保存；外网识图请确保该地址可被模型服务访问。
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
        <header className="settings-group-header">
          <h3 className="settings-group-title">嵌入模型</h3>
          <p className="settings-group-hint">用于向量检索；可从目录筛选模型名。</p>
        </header>
        <div className="settings-embed-row">
          <div className="settings-embed-model">
            <ModelNameField
              value={embedModel}
              disabled={saving}
              applyCapabilities={false}
              catalogKind="embedding"
              label="模型名称"
              onPatch={(patch) => {
                if (patch.model != null) onEmbedModelChange(patch.model);
              }}
            />
          </div>
          <button
            type="button"
            className={`settings-endpoint-toggle${endpointExpanded.embed ? " settings-endpoint-toggle--on" : ""}`}
            aria-pressed={endpointExpanded.embed}
            title={
              endpointExpanded.embed
                ? "独立端点已开：使用嵌入专用 URL / Key"
                : "独立端点已关：使用默认 URL / Key"
            }
            disabled={saving}
            onClick={() => {
              const on = !endpointExpanded.embed;
              setEndpointExpanded((prev) => ({ ...prev, embed: on }));
              if (!on) {
                onEmbedBaseUrlChange("");
                setSecretInputs((prev) => ({ ...prev, embed_api_key: "" }));
              }
            }}
          >
            独立
          </button>
        </div>
        {endpointExpanded.embed ? (
          <div className="settings-field-row">
            <label className="settings-field">
              <span>Base URL</span>
              <input
                value={embedBaseUrl}
                onChange={(e) => onEmbedBaseUrlChange(e.target.value)}
                disabled={saving}
                placeholder="https://…"
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
        <header className="settings-group-header">
          <h3 className="settings-group-title">搜索密钥</h3>
          <p className="settings-group-hint">用于联网搜索工具，可选配置。</p>
        </header>
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
