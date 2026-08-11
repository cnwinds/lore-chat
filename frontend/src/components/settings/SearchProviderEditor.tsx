import type { CooldownStatus } from "./settingsTypes";

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
    <section className="settings-group settings-chain">
      <header className="settings-group-header">
        <h3 className="settings-group-title">搜索提供商</h3>
        <p className="settings-group-hint">
          用于联网搜索工具。按需添加；列表顺序即优先级，出问题会冷却并切换下一家。每种类型只能添加一次。
        </p>
      </header>
      <div className="settings-chain-list">
        {providers.map((p, i) => {
          const st = cooldown[p.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          return (
            <article
              key={p.id}
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
                  <span className="settings-search-provider-name">{labelOf(p.provider)}</span>
                </div>
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
                    onClick={() => onClearCooldown(p.id)}
                  >
                    立即重试
                  </button>
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
    </section>
  );
}
