import { useMemo } from "react";
import type { CooldownStatus } from "./settingsTypes";
import { ProviderCooldownBar } from "./ProviderCooldownBar";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";

export type SearchProviderId = "tavily" | "serper" | "brave";

export const SEARCH_PROVIDER_OPTIONS: {
  id: SearchProviderId;
  label: string;
}[] = [
  { id: "tavily", label: "Tavily" },
  { id: "serper", label: "Serper" },
  { id: "brave", label: "Brave Search" },
];

export type SearchProviderDraft = {
  id: string;
  provider: SearchProviderId;
  /** 用户新输入；留空表示不改 */
  api_key: string;
  /** 服务端脱敏展示，作 placeholder */
  api_key_masked?: string;
};

type Props = {
  providers: SearchProviderDraft[];
  onChange: (next: SearchProviderDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (providerId: string) => void;
  saving: boolean;
};

export function SearchProviderEditor({
  providers,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
}: Props) {
  const used = new Set(providers.map((p) => p.provider));
  const available = SEARCH_PROVIDER_OPTIONS.filter((o) => !used.has(o.id));
  const ids = useMemo(() => providers.map((p) => p.id), [providers]);
  const { isOpen, toggle } = useSettingsItemFold(ids);

  function updateAt(i: number, patch: Partial<SearchProviderDraft>) {
    onChange(providers.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= providers.length) return;
    const next = [...providers];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }

  function addProvider(provider: SearchProviderId) {
    if (used.has(provider)) return;
    onChange([...providers, { id: provider, provider, api_key: "" }]);
  }

  const labelOf = (id: SearchProviderId) =>
    SEARCH_PROVIDER_OPTIONS.find((o) => o.id === id)?.label ?? id;

  return (
    <SettingsFoldSection title="搜索提供商" count={providers.length}>
      <div className="settings-chain-list">
        {providers.map((p, i) => {
          const st = cooldown[p.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          const open = isOpen(p.id);
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
                  title={labelOf(p.provider)}
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
      {available.length > 0 ? (
        <div className="settings-search-add-row">
          <label className="settings-field settings-search-add-field">
            <span className="visually-hidden">添加搜索提供商</span>
            <select
              value=""
              disabled={saving}
              onChange={(e) => {
                const v = e.target.value as SearchProviderId;
                if (v) addProvider(v);
              }}
            >
              <option value="" disabled>
                + 添加搜索提供商
              </option>
              {available.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : (
        <p className="settings-group-hint">已添加全部可用类型。</p>
      )}
    </SettingsFoldSection>
  );
}
