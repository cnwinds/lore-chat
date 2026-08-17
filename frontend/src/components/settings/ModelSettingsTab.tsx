import { useEffect, useMemo, useRef, useState } from "react";
import { listProviderModels, type ModelCatalogItem } from "../../api";
import { newId } from "../../utils/id";
import {
  SearchProviderEditor,
  type SearchProviderDraft,
} from "./SearchProviderEditor";
import {
  ImageProviderEditor,
  type ImageProviderDraft,
} from "./ImageProviderEditor";
import type { CooldownStatus } from "./settingsTypes";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";
import { draftChainNeedsSetup } from "./settingsAttention";
import {
  EMBED_PROVIDER_DEFAULT_BASE_URL,
  EMBED_PROVIDER_OPTIONS,
  LLM_PROVIDER_DEFAULT_BASE_URL,
  LLM_PROVIDER_OPTIONS,
  candidateFromProvider,
  embedCandidateFromProvider,
  embedProviderLabel,
  inferProviderFromBaseUrl,
  llmProviderLabel,
  maskApiKeyPlaceholder,
  parseProviderPresetId,
  type EmbedCandidateDraft,
  type EmbedProviderPresetId,
  type LlmProviderPresetId,
  type ModelCandidateDraft,
} from "./providerPresets";

export type { SearchProviderDraft, SearchProviderId } from "./SearchProviderEditor";
export { SEARCH_PROVIDER_OPTIONS } from "./SearchProviderEditor";
export type { ImageProviderDraft, ImageProviderId } from "./ImageProviderEditor";
export { IMAGE_PROVIDER_OPTIONS } from "./ImageProviderEditor";
export type { CooldownStatus } from "./settingsTypes";
export type {
  EmbedCandidateDraft,
  EmbedProviderPresetId,
  LlmProviderPresetId,
  ModelCandidateDraft,
} from "./providerPresets";
export {
  EMBED_PROVIDER_DEFAULT_BASE_URL,
  EMBED_PROVIDER_OPTIONS,
  LLM_PROVIDER_DEFAULT_BASE_URL,
  LLM_PROVIDER_OPTIONS,
  candidateFromProvider,
  embedCandidateFromProvider,
  embedCandidatesFromLegacy,
  embedProviderLabel,
  emptyCandidate,
  emptyEmbedCandidate,
  inferEmbedProviderFromBaseUrl,
  inferProviderFromBaseUrl,
  llmProviderLabel,
  maskApiKeyPlaceholder,
  parseEmbedCandidates,
  parseEmbedProviderPresetId,
  parseProviderPresetId,
} from "./providerPresets";

/** 与后端 effort.supported_efforts 对齐 */
export function supportedEfforts(model: string, protocol?: string): string[] {
  const mid = model.trim().toLowerCase();
  const proto = (protocol || "").trim().toLowerCase();
  if (proto === "agnes" || mid.startsWith("agnes-")) {
    return [];
  }
  if (proto === "deepseek" || proto === "qwen") {
    return ["low", "medium", "high", "max"];
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
  if (mid.startsWith("deepseek-") || mid.startsWith("qwen")) {
    return ["low", "medium", "high", "max"];
  }
  if (mid.startsWith("glm")) {
    return ["low", "medium", "high", "max"];
  }
  return ["low", "medium", "high"];
}

export function defaultEffort(model: string, protocol?: string): string {
  const opts = supportedEfforts(model, protocol);
  if (!opts.length) return "medium";
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

export function pickEffortInOptions(effort: string, opts: string[]): string {
  if (!opts.length) return effort || "medium";
  if (opts.includes(effort)) return effort;
  if (opts.includes("medium")) return "medium";
  return opts[0];
}

export function parseCandidates(raw: unknown): ModelCandidateDraft[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => {
      const model = str(x.model);
      const protocol = str(x.thinking_protocol) || "none";
      // 空数组 = 目录声明无强度档，不得回落启发式臆造
      const opts = Array.isArray(x.effort_options)
        ? x.effort_options.map(String)
        : supportedEfforts(model, protocol);
      const effort = pickEffortInOptions(str(x.effort), opts);
      const base = str(x.base_url);
      const rawKey = typeof x.api_key === "string" ? x.api_key.trim() : "";
      const hadKey = Boolean(rawKey);
      const provider =
        parseProviderPresetId(x.provider) ?? inferProviderFromBaseUrl(base);
      return {
        id: str(x.id) || newId().slice(0, 12),
        model,
        base_url: base,
        api_key: "",
        ...(hadKey ? { api_key_masked: maskApiKeyPlaceholder(rawKey) } : {}),
        provider,
        image: Boolean(x.image),
        thinking: Boolean(x.thinking),
        effort,
        effort_options: opts,
        image_wire: x.image_wire === "url" ? "url" : "data",
        thinking_protocol: protocol,
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

/** 与后端 catalog 前缀启发对齐（含 glm 思考）。 */
export function inferCapsFromModel(
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
  if (mid.startsWith("glm")) {
    return {
      image: false,
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
  const opts = Array.isArray(item.effort_options)
    ? item.effort_options.map(String)
    : supportedEfforts(item.id, item.thinking_protocol);
  return {
    model: item.id,
    image: item.image,
    thinking: item.thinking,
    effort: pickEffortInOptions(String(item.effort || ""), opts),
    effort_options: opts,
    image_wire: item.image_wire,
    thinking_protocol: item.thinking_protocol,
  };
}

type ModelNameFieldProps = {
  value: string;
  disabled: boolean;
  baseUrl?: string;
  apiKey?: string;
  candidateId?: string;
  capsUserEdited?: boolean;
  /** false：仅改模型名（嵌入模型）；默认 true 会带上能力 */
  applyCapabilities?: boolean;
  /** 目录筛选：llm 排除嵌入/生图；embedding 仅嵌入；image 仅生图 */
  catalogKind?: "all" | "llm" | "embedding" | "image";
  label?: string;
  onPatch: (patch: Partial<ModelCandidateDraft>) => void;
};

function ModelNameField({
  value,
  disabled,
  baseUrl = "",
  apiKey = "",
  candidateId,
  capsUserEdited,
  applyCapabilities = true,
  catalogKind = "llm",
  label = "模型名称",
  onPatch,
}: ModelNameFieldProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(value);
  const [allItems, setAllItems] = useState<ModelCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const hasBase = Boolean(baseUrl.trim());
  const fieldDisabled = disabled || !hasBase;

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return allItems;
    return allItems.filter(
      (it) =>
        it.id.toLowerCase().includes(needle) ||
        (it.name || "").toLowerCase().includes(needle) ||
        (it.provider || "").toLowerCase().includes(needle),
    );
  }, [allItems, q]);

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
    if (!open || !hasBase) return;
    const my = ++seq.current;
    const handle = window.setTimeout(() => {
      setLoading(true);
      void listProviderModels({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || null,
        candidate_id: candidateId || null,
        kind: catalogKind,
        limit: 100,
      })
        .then((res) => {
          if (seq.current !== my) return;
          setAllItems(res.items || []);
          if (res.source === "provider") {
            setHint(`接口模型 · ${(res.items || []).length} 条`);
          } else {
            setHint(
              `无法拉取接口列表，已列出已知模型${
                res.error ? `（${String(res.error).slice(0, 80)}）` : ""
              }`,
            );
          }
        })
        .catch(() => {
          if (seq.current !== my) return;
          setAllItems([]);
          setHint("模型列表查询失败，可手填模型名");
        })
        .finally(() => {
          if (seq.current === my) setLoading(false);
        });
    }, 120);
    return () => window.clearTimeout(handle);
  }, [open, catalogKind, baseUrl, apiKey, candidateId, hasBase]);

  function applyTyped(name: string) {
    if (!applyCapabilities) {
      onPatch({ model: name });
      return;
    }
    const hit = allItems.find((it) => it.id.toLowerCase() === name.toLowerCase());
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
          disabled={fieldDisabled}
          placeholder={hasBase ? "点击选择或搜索接口模型" : "请先填写 Base URL"}
          autoComplete="off"
          onFocus={() => {
            if (hasBase) setOpen(true);
          }}
          onChange={(e) => {
            setQ(e.target.value);
            if (hasBase) setOpen(true);
            onPatch({ model: e.target.value });
          }}
          onBlur={() => {
            window.setTimeout(() => applyTyped(q.trim()), 120);
          }}
        />
      </label>
      {open && hasBase ? (
        <div className="settings-model-picker-menu" role="listbox">
          <div className="settings-model-picker-meta">
            {loading ? "加载模型列表…" : hint || "输入关键字过滤"}
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

function ImageCapIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="9" cy="11" r="2" />
      <path d="m21 15-4.5-4.5L9 18" />
    </svg>
  );
}

function ThinkingCapIcon({ size = 15 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
      <path d="M17.599 6.5a3 3 0 0 0 .399-1.375" />
      <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5" />
      <path d="M3.337 7.5a4 4 0 0 0-.2 2.4" />
      <path d="M20.863 9.9a4 4 0 0 0-.2-2.4" />
      <path d="M20.863 14.1a4 4 0 0 1-.2 2.4" />
      <path d="M3.337 16.5a4 4 0 0 1-.2-2.4" />
      <path d="M8.664 20.5a4 4 0 0 0 6.672 0" />
    </svg>
  );
}

function ImageWireSwitch({
  value,
  disabled,
  onChange,
}: {
  value: "data" | "url";
  disabled?: boolean;
  onChange: (v: "data" | "url") => void;
}) {
  const isData = value === "data";
  return (
    <button
      type="button"
      className={`settings-wire-switch${isData ? " is-data" : " is-url"}`}
      disabled={disabled}
      onClick={() => onChange(isData ? "url" : "data")}
      title={isData ? "识图传输：data（点击改为 url）" : "识图传输：url（点击改为 data）"}
      aria-label={isData ? "识图传输：data" : "识图传输：url"}
      aria-pressed={!isData}
    >
      <span className="settings-wire-switch-track" aria-hidden>
        <span className="settings-wire-switch-label settings-wire-switch-label--data">data</span>
        <span className="settings-wire-switch-label settings-wire-switch-label--url">url</span>
        <span className="settings-wire-switch-knob" />
      </span>
    </button>
  );
}

type ChainEditorProps = {
  title: string;
  candidates: ModelCandidateDraft[];
  onChange: (next: ModelCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
  attention?: boolean;
};

function ChainEditor({
  title,
  candidates,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
  attention = false,
}: ChainEditorProps) {
  const ids = candidates.map((c) => c.id);
  const { isOpen, toggle } = useSettingsItemFold(ids);

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
    <SettingsFoldSection
      title={title}
      count={candidates.length}
      attention={attention}
    >
      <div className="settings-chain-list">
        {candidates.map((c, i) => {
          const st = cooldown[c.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          const open = isOpen(c.id);
          const rowTitle = c.model.trim()
            ? `${llmProviderLabel(c.provider)} · ${c.model.trim()}`
            : llmProviderLabel(c.provider);
          return (
            <article
              key={c.id}
              className={[
                "settings-model-candidate",
                open ? "" : "settings-model-candidate--folded",
                i === 0 ? "settings-model-candidate--primary" : "",
                disabled ? "settings-model-candidate--disabled" : "",
                cooling ? "settings-model-candidate--cooling" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <div className="settings-model-candidate-head">
                <SettingsCandidateFoldToggle
                  open={open}
                  onToggle={() => toggle(c.id)}
                  title={rowTitle}
                  titleAttr={c.id}
                  priority={i + 1}
                  primary={i === 0}
                />
                <div className="settings-model-candidate-actions">
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

              {open ? (
                <div className="settings-model-candidate-body">
                  <div className="settings-field-row">
                    <label className="settings-field">
                      <span>Base URL</span>
                      <input
                        value={c.base_url}
                        onChange={(e) => updateAt(i, { base_url: e.target.value })}
                        disabled={saving || c.provider !== "custom"}
                        readOnly={c.provider !== "custom"}
                        placeholder={
                          c.provider === "custom"
                            ? "https://…"
                            : LLM_PROVIDER_DEFAULT_BASE_URL[
                                c.provider as Exclude<LlmProviderPresetId, "custom">
                              ]
                        }
                        title={
                          c.provider !== "custom"
                            ? "已选厂家，地址由预设决定；改用「自定义」可编辑"
                            : undefined
                        }
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
                        placeholder={c.api_key_masked || "未设置"}
                      />
                    </label>
                  </div>

                  <ModelNameField
                    value={c.model}
                    disabled={saving}
                    baseUrl={c.base_url}
                    apiKey={c.api_key}
                    candidateId={c.id}
                    capsUserEdited={c.caps_user_edited}
                    catalogKind="llm"
                    onPatch={(patch) => updateAt(i, patch)}
                  />

                  <div className="settings-model-toolbar">
                    <div className="settings-model-caps">
                      <button
                        type="button"
                        className={`settings-cap-icon-btn${c.image ? " settings-cap-icon-btn--on" : ""}`}
                        disabled={saving}
                        aria-pressed={c.image}
                        aria-label={c.image ? "识图：开" : "识图：关"}
                        title={c.image ? "识图：开" : "识图：关"}
                        onClick={() =>
                          updateAt(i, { image: !c.image, caps_user_edited: true })
                        }
                      >
                        <ImageCapIcon />
                      </button>
                      <ImageWireSwitch
                        value={c.image_wire}
                        disabled={saving || !c.image}
                        onChange={(image_wire) =>
                          updateAt(i, { image_wire, caps_user_edited: true })
                        }
                      />
                      <button
                        type="button"
                        className={`settings-cap-icon-btn${c.thinking ? " settings-cap-icon-btn--on" : ""}`}
                        disabled={saving}
                        aria-pressed={c.thinking}
                        aria-label={c.thinking ? "思考：开" : "思考：关"}
                        title={c.thinking ? "思考：开" : "思考：关"}
                        onClick={() =>
                          updateAt(i, { thinking: !c.thinking, caps_user_edited: true })
                        }
                      >
                        <ThinkingCapIcon />
                      </button>
                      {c.effort_options.length > 0 ? (
                        <label className="settings-cap-select">
                          <span>强度</span>
                          <select
                            value={pickEffortInOptions(c.effort, c.effort_options)}
                            onChange={(e) => updateAt(i, { effort: e.target.value })}
                            disabled={saving || !c.thinking}
                          >
                            {c.effort_options.map((lv) => (
                              <option key={lv} value={lv}>
                                {lv}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                    </div>
                  </div>

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
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      <div className="settings-search-add-row">
        <label className="settings-field settings-search-add-field">
          <span className="visually-hidden">添加候选</span>
          <select
            value=""
            disabled={saving}
            onChange={(e) => {
              const v = e.target.value as LlmProviderPresetId;
              if (v) onChange([...candidates, candidateFromProvider(v)]);
            }}
          >
            <option value="" disabled>
              + 添加候选（选择厂家）
            </option>
            {LLM_PROVIDER_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </SettingsFoldSection>
  );
}

type EmbedChainEditorProps = {
  candidates: EmbedCandidateDraft[];
  onChange: (next: EmbedCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
  attention?: boolean;
};

function EmbedChainEditor({
  candidates,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
  attention = false,
}: EmbedChainEditorProps) {
  const ids = candidates.map((c) => c.id);
  const { isOpen, toggle } = useSettingsItemFold(ids);

  function updateAt(i: number, patch: Partial<EmbedCandidateDraft>) {
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
    <SettingsFoldSection
      title="嵌入模型"
      count={candidates.length}
      attention={attention}
    >
      <div className="settings-chain-list">
        {candidates.map((c, i) => {
          const st = cooldown[c.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          const open = isOpen(c.id);
          const rowTitle = c.model.trim()
            ? `${embedProviderLabel(c.provider)} · ${c.model.trim()}`
            : embedProviderLabel(c.provider);
          return (
            <article
              key={c.id}
              className={[
                "settings-model-candidate",
                open ? "" : "settings-model-candidate--folded",
                i === 0 ? "settings-model-candidate--primary" : "",
                disabled ? "settings-model-candidate--disabled" : "",
                cooling ? "settings-model-candidate--cooling" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <div className="settings-model-candidate-head">
                <SettingsCandidateFoldToggle
                  open={open}
                  onToggle={() => toggle(c.id)}
                  title={rowTitle}
                  titleAttr={c.id}
                  priority={i + 1}
                  primary={i === 0}
                />
                <div className="settings-model-candidate-actions">
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

              {open ? (
                <div className="settings-model-candidate-body">
                  <div className="settings-field-row">
                    <label className="settings-field">
                      <span>Base URL</span>
                      <input
                        value={c.base_url}
                        onChange={(e) => updateAt(i, { base_url: e.target.value })}
                        disabled={saving || c.provider !== "custom"}
                        readOnly={c.provider !== "custom"}
                        placeholder={
                          c.provider === "custom"
                            ? "https://…"
                            : EMBED_PROVIDER_DEFAULT_BASE_URL[
                                c.provider as Exclude<EmbedProviderPresetId, "custom">
                              ]
                        }
                        title={
                          c.provider !== "custom"
                            ? "已选厂家，地址由预设决定；改用「自定义」可编辑"
                            : undefined
                        }
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
                        placeholder={c.api_key_masked || "未设置"}
                      />
                    </label>
                  </div>

                  <ModelNameField
                    value={c.model}
                    disabled={saving}
                    baseUrl={c.base_url}
                    apiKey={c.api_key}
                    candidateId={c.id}
                    applyCapabilities={false}
                    catalogKind="embedding"
                    label="模型名称"
                    onPatch={(patch) => {
                      if (patch.model != null) updateAt(i, { model: patch.model });
                    }}
                  />

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
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      <div className="settings-search-add-row">
        <label className="settings-field settings-search-add-field">
          <span className="visually-hidden">添加嵌入候选</span>
          <select
            value=""
            disabled={saving}
            onChange={(e) => {
              const v = e.target.value as EmbedProviderPresetId;
              if (v) onChange([...candidates, embedCandidateFromProvider(v)]);
            }}
          >
            <option value="" disabled>
              + 添加候选（选择厂家）
            </option>
            {EMBED_PROVIDER_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </SettingsFoldSection>
  );
}

type Props = {
  publicBaseUrl: string;
  onPublicBaseUrlChange: (v: string) => void;
  chatModels: ModelCandidateDraft[];
  onChatModelsChange: (v: ModelCandidateDraft[]) => void;
  utilityModels: ModelCandidateDraft[];
  onUtilityModelsChange: (v: ModelCandidateDraft[]) => void;
  embedModels: EmbedCandidateDraft[];
  onEmbedModelsChange: (v: EmbedCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  searchProviders: SearchProviderDraft[];
  onSearchProvidersChange: (v: SearchProviderDraft[]) => void;
  searchCooldown: CooldownStatus;
  onClearSearchCooldown: (providerId: string) => void;
  imageProviders: ImageProviderDraft[];
  onImageProvidersChange: (v: ImageProviderDraft[]) => void;
  imageCooldown: CooldownStatus;
  onClearImageCooldown: (providerId: string) => void;
  saving: boolean;
};

export function ModelSettingsTab({
  publicBaseUrl,
  onPublicBaseUrlChange,
  chatModels,
  onChatModelsChange,
  utilityModels,
  onUtilityModelsChange,
  embedModels,
  onEmbedModelsChange,
  cooldown,
  onClearCooldown,
  searchProviders,
  onSearchProvidersChange,
  searchCooldown,
  onClearSearchCooldown,
  imageProviders,
  onImageProvidersChange,
  imageCooldown,
  onClearImageCooldown,
  saving,
}: Props) {
  return (
    <>
      <ChainEditor
        title="对话模型"
        candidates={chatModels}
        onChange={onChatModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(chatModels)}
      />

      <ChainEditor
        title="辅助模型"
        candidates={utilityModels}
        onChange={onUtilityModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(utilityModels)}
      />

      <EmbedChainEditor
        candidates={embedModels}
        onChange={onEmbedModelsChange}
        cooldown={cooldown}
        onClearCooldown={onClearCooldown}
        saving={saving}
        attention={draftChainNeedsSetup(embedModels)}
      />

      <SearchProviderEditor
        providers={searchProviders}
        onChange={onSearchProvidersChange}
        cooldown={searchCooldown}
        onClearCooldown={onClearSearchCooldown}
        saving={saving}
      />

      <ImageProviderEditor
        providers={imageProviders}
        onChange={onImageProvidersChange}
        cooldown={imageCooldown}
        onClearCooldown={onClearImageCooldown}
        saving={saving}
      />

      <div className="settings-group">
        <header className="settings-group-header">
          <h3 className="settings-group-title">识图公网地址</h3>
        </header>
        <label className="settings-field">
          <span>Public Base URL</span>
          <input
            value={publicBaseUrl}
            onChange={(e) => onPublicBaseUrlChange(e.target.value)}
            disabled={saving}
            placeholder="https://your-host"
          />
        </label>
      </div>
    </>
  );
}
