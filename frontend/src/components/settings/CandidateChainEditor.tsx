import { useEffect, useMemo, useRef, useState } from "react";
import { listProviderModels, type ModelCatalogItem } from "../../api";
import type { CooldownStatus } from "./settingsTypes";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";
import { ProviderApiKeyLabel } from "./ProviderApiKeyLabel";
import { resolveModelCaps, capsFromCatalogItem } from "./modelCapabilities";
import { pickEffortInOptions } from "./modelChainDrafts";
import {
  LLM_PROVIDER_DEFAULT_BASE_URL,
  LLM_PROVIDER_OPTIONS,
  candidateFromProvider,
  llmProviderLabel,
  type LlmProviderPresetId,
  type ModelCandidateDraft,
} from "./providerPresets";

function videoCapLabel(maxVideos?: number): string {
  if (typeof maxVideos === "number" && maxVideos > 1) {
    return `视频×${maxVideos}`;
  }
  return "视频";
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

export function ModelNameField({
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

  async function applyTyped(name: string) {
    if (!applyCapabilities) {
      onPatch({ model: name });
      return;
    }
    const hit = allItems.find((it) => it.id.toLowerCase() === name.toLowerCase());
    if (hit && !capsUserEdited) {
      onPatch({ ...capsFromCatalogItem(hit), caps_user_edited: false });
      return;
    }
    const looked = await resolveModelCaps(name, baseUrl);
    if (capsUserEdited) {
      onPatch({
        model: name,
        thinking_protocol: looked.thinking_protocol,
        effort_options: looked.effort_options,
      });
    } else {
      onPatch({
        model: name,
        ...looked,
        effort: pickEffortInOptions(looked.effort, looked.effort_options),
        caps_user_edited: false,
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
                        effort: pickEffortInOptions(
                          fromCat.effort,
                          fromCat.effort_options,
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
                  {it.video ? <em>{videoCapLabel(it.max_videos)}</em> : null}
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

function VideoCapIcon({ size = 15 }: { size?: number }) {
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
      <path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5" />
      <rect x="2" y="6" width="14" height="12" rx="2" />
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

function VideoWireSwitch({
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
      title={isData ? "视频传输：data（点击改为 url）" : "视频传输：url（点击改为 data）"}
      aria-label={isData ? "视频传输：data" : "视频传输：url"}
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

type CandidateChainEditorProps = {
  title: string;
  candidates: ModelCandidateDraft[];
  onChange: (next: ModelCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
  attention?: boolean;
  hydrated?: boolean;
};

export function CandidateChainEditor({
  title,
  candidates,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
  attention = false,
  hydrated = true,
}: CandidateChainEditorProps) {
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
      defaultOpen={hydrated && (candidates.length === 0 || attention)}
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
                    disabled={saving}
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
                      <ProviderApiKeyLabel providerId={c.provider} />
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
                        className={`settings-cap-icon-btn${c.video ? " settings-cap-icon-btn--on" : ""}`}
                        disabled={saving}
                        aria-pressed={c.video}
                        aria-label={
                          c.video
                            ? `${videoCapLabel(c.max_videos)}：开`
                            : `${videoCapLabel(c.max_videos)}：关`
                        }
                        title={
                          c.video
                            ? `${videoCapLabel(c.max_videos)}：开`
                            : `${videoCapLabel(c.max_videos)}：关`
                        }
                        onClick={() =>
                          updateAt(i, { video: !c.video, caps_user_edited: true })
                        }
                      >
                        <VideoCapIcon />
                      </button>
                      <VideoWireSwitch
                        value={c.video_wire}
                        disabled={saving || !c.video}
                        onChange={(video_wire) =>
                          updateAt(i, { video_wire, caps_user_edited: true })
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

