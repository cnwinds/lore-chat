import { useMemo } from "react";
import type { CooldownStatus } from "./settingsTypes";
import { ProviderCooldownBar } from "./ProviderCooldownBar";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";
import { SettingsChainGrip, useSettingsChainDrag } from "./SettingsChainDrag";
import { ProviderApiKeyLabel } from "./ProviderApiKeyLabel";

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
  const { articleProps, gripProps } = useSettingsChainDrag(
    providers,
    onChange,
    saving,
  );

  function updateAt(i: number, patch: Partial<SearchProviderDraft>) {
    onChange(providers.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
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
          const drag = articleProps(p.id, i);
          return (
            <article
              key={p.id}
              className={[
                "settings-model-candidate",
                open ? "" : "settings-model-candidate--folded",
                i === 0 ? "settings-model-candidate--primary" : "",
                disabled ? "settings-model-candidate--disabled" : "",
                cooling ? "settings-model-candidate--cooling" : "",
                drag.extraClass,
              ]
                .filter(Boolean)
                .join(" ")}
              onDragOver={drag.onDragOver}
              onDrop={drag.onDrop}
            >
              <div className="settings-model-candidate-head">
                <SettingsChainGrip {...gripProps(p.id, i)} />
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
                    <ProviderApiKeyLabel providerId={p.provider} />
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
