import { useEffect, useMemo, useRef, useState } from "react";
import { listProviderModels, type ModelCatalogItem } from "../../api";
import type { CooldownStatus } from "./settingsTypes";
import { ProviderCooldownBar } from "./ProviderCooldownBar";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";

export type ImageProviderId = "openai" | "zhipu" | "bailian" | "agnes" | "custom";

/** 与 backend `imagegen/providers._DEFAULT_BASE_URLS` 对齐 */
export const IMAGE_PROVIDER_DEFAULT_BASE_URL: Record<
  Exclude<ImageProviderId, "custom">,
  string
> = {
  openai: "https://api.openai.com/v1",
  zhipu: "https://open.bigmodel.cn/api/paas/v4",
  bailian: "https://dashscope.aliyuncs.com",
  agnes: "https://apihub.agnes-ai.com/v1",
};

/** 与 backend `imagegen/providers._DEFAULT_MODELS` 对齐 */
export const IMAGE_PROVIDER_DEFAULT_MODEL: Record<
  Exclude<ImageProviderId, "custom">,
  string
> = {
  openai: "dall-e-3",
  zhipu: "cogview-4",
  bailian: "wanx-v1",
  agnes: "agnes-image-2.1-flash",
};

export const IMAGE_PROVIDER_OPTIONS: {
  id: ImageProviderId;
  label: string;
}[] = [
  { id: "openai", label: "OpenAI Images" },
  { id: "zhipu", label: "智谱 CogView" },
  { id: "bailian", label: "百炼万相" },
  { id: "agnes", label: "Agnes Image" },
  { id: "custom", label: "自定义" },
];

export type ImageProviderDraft = {
  id: string;
  provider: ImageProviderId;
  api_key: string;
  api_key_masked?: string;
  base_url: string;
  model: string;
};

type Props = {
  providers: ImageProviderDraft[];
  onChange: (next: ImageProviderDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (providerId: string) => void;
  saving: boolean;
};

function nextEntryId(provider: ImageProviderId, existing: ImageProviderDraft[]): string {
  const ids = new Set(existing.map((p) => p.id));
  if (!ids.has(provider)) return provider;
  let n = 2;
  while (ids.has(`${provider}-${n}`)) n += 1;
  return `${provider}-${n}`;
}

/** 拉 /models 用的根：百炼生图根常无 /models，改走兼容模式列表。 */
export function imageModelsListBaseUrl(
  provider: ImageProviderId,
  baseUrl: string,
): string {
  if (provider === "custom") {
    return (baseUrl || "").trim().replace(/\/+$/, "");
  }
  const fallback = IMAGE_PROVIDER_DEFAULT_BASE_URL[provider];
  const root = (baseUrl.trim() || fallback).replace(/\/+$/, "");
  if (provider === "bailian" && !/compatible-mode/i.test(root)) {
    return "https://dashscope.aliyuncs.com/compatible-mode/v1";
  }
  return root;
}

type ImageModelNameFieldProps = {
  value: string;
  disabled: boolean;
  provider: ImageProviderId;
  baseUrl: string;
  apiKey: string;
  candidateId: string;
  placeholder?: string;
  onChange: (model: string) => void;
};

function ImageModelNameField({
  value,
  disabled,
  provider,
  baseUrl,
  apiKey,
  candidateId,
  placeholder,
  onChange,
}: ImageModelNameFieldProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(value);
  const [allItems, setAllItems] = useState<ModelCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);
  const listBase = imageModelsListBaseUrl(provider, baseUrl);
  const hasBase = Boolean(listBase.trim());
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
        base_url: listBase,
        api_key: apiKey.trim() || null,
        candidate_id: candidateId || null,
        kind: "image",
        limit: 100,
      })
        .then((res) => {
          if (seq.current !== my) return;
          setAllItems(res.items || []);
          if (res.source === "provider") {
            setHint(`接口模型 · ${(res.items || []).length} 条`);
          } else {
            setHint(
              `无法拉取接口列表，已列出已知生图模型${
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
  }, [open, listBase, apiKey, candidateId, hasBase]);

  return (
    <div className="settings-model-picker" ref={wrapRef}>
      <label className="settings-field">
        <span>模型名称</span>
        <input
          value={q}
          disabled={fieldDisabled}
          placeholder={
            hasBase
              ? placeholder || "点击选择或搜索接口模型"
              : "请先填写 Base URL"
          }
          autoComplete="off"
          onFocus={() => {
            if (hasBase) setOpen(true);
          }}
          onChange={(e) => {
            setQ(e.target.value);
            if (hasBase) setOpen(true);
            onChange(e.target.value);
          }}
          onBlur={() => {
            window.setTimeout(() => onChange(q.trim()), 120);
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
                  onChange(it.id);
                  setQ(it.id);
                  setOpen(false);
                }}
              >
                <span className="settings-model-picker-id">{it.id}</span>
                <span className="settings-model-picker-sub">
                  {it.provider}
                  {it.name && it.name !== it.id ? ` · ${it.name}` : ""}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

export function ImageProviderEditor({
  providers,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
}: Props) {
  const ids = useMemo(() => providers.map((p) => p.id), [providers]);
  const { isOpen, toggle } = useSettingsItemFold(ids);

  function updateAt(i: number, patch: Partial<ImageProviderDraft>) {
    onChange(providers.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= providers.length) return;
    const next = [...providers];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }

  function addProvider(provider: ImageProviderId) {
    if (provider === "custom") {
      onChange([
        ...providers,
        {
          id: nextEntryId(provider, providers),
          provider: "custom",
          api_key: "",
          base_url: "",
          model: "",
        },
      ]);
      return;
    }
    onChange([
      ...providers,
      {
        id: nextEntryId(provider, providers),
        provider,
        api_key: "",
        base_url: IMAGE_PROVIDER_DEFAULT_BASE_URL[provider],
        model: IMAGE_PROVIDER_DEFAULT_MODEL[provider],
      },
    ]);
  }

  const labelOf = (id: ImageProviderId) =>
    IMAGE_PROVIDER_OPTIONS.find((o) => o.id === id)?.label ?? id;

  return (
    <SettingsFoldSection title="生图模型" count={providers.length}>
      <div className="settings-chain-list">
        {providers.map((p, i) => {
          const st = cooldown[p.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          const open = isOpen(p.id);
          const title =
            p.model.trim() !== ""
              ? `${labelOf(p.provider)} · ${p.model.trim()}`
              : labelOf(p.provider);
          return (
            <article
              key={p.id}
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
                  onToggle={() => toggle(p.id)}
                  title={title}
                  titleAttr={p.id}
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
                    disabled={saving || i === providers.length - 1}
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
                    onClick={() => onChange(providers.filter((_, idx) => idx !== i))}
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
                        type="text"
                        autoComplete="off"
                        value={p.base_url}
                        onChange={(e) =>
                          updateAt(i, { base_url: e.target.value })
                        }
                        disabled={saving || p.provider !== "custom"}
                        readOnly={p.provider !== "custom"}
                        placeholder={
                          p.provider === "custom"
                            ? "https://…"
                            : IMAGE_PROVIDER_DEFAULT_BASE_URL[p.provider]
                        }
                        title={
                          p.provider !== "custom"
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
                        value={p.api_key}
                        onChange={(e) => updateAt(i, { api_key: e.target.value })}
                        disabled={saving}
                        placeholder={p.api_key_masked || "未设置"}
                      />
                    </label>
                  </div>

                  <ImageModelNameField
                    value={p.model}
                    disabled={saving}
                    provider={p.provider}
                    baseUrl={p.base_url}
                    apiKey={p.api_key}
                    candidateId={p.id}
                    placeholder={
                      (p.provider !== "custom"
                        ? IMAGE_PROVIDER_DEFAULT_MODEL[p.provider]
                        : "") || "点击选择或搜索接口模型"
                    }
                    onChange={(model) => updateAt(i, { model })}
                  />

                  <ProviderCooldownBar
                    status={st}
                    saving={saving}
                    onClear={() => onClearCooldown(p.id)}
                  />
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      <div className="settings-search-add-row">
        <label className="settings-field settings-search-add-field">
          <span className="visually-hidden">添加生图模型</span>
          <select
            value=""
            disabled={saving}
            onChange={(e) => {
              const v = e.target.value as ImageProviderId;
              if (v) addProvider(v);
            }}
          >
            <option value="" disabled>
              + 添加生图模型
            </option>
            {IMAGE_PROVIDER_OPTIONS.map((o) => (
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
