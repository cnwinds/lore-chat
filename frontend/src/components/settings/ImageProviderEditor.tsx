import type { CooldownStatus } from "./settingsTypes";
import { ProviderCooldownBar } from "./ProviderCooldownBar";

export type ImageProviderId = "openai" | "zhipu" | "bailian";

export const IMAGE_PROVIDER_OPTIONS: {
  id: ImageProviderId;
  label: string;
}[] = [
  { id: "openai", label: "OpenAI Images" },
  { id: "zhipu", label: "智谱 CogView" },
  { id: "bailian", label: "百炼万相" },
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

export function ImageProviderEditor({
  providers,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
}: Props) {
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
    onChange([
      ...providers,
      {
        id: nextEntryId(provider, providers),
        provider,
        api_key: "",
        base_url: "",
        model: "",
      },
    ]);
  }

  const labelOf = (id: ImageProviderId) =>
    IMAGE_PROVIDER_OPTIONS.find((o) => o.id === id)?.label ?? id;

  return (
    <section className="settings-group settings-chain">
      <header className="settings-group-header">
        <h3 className="settings-group-title">生图提供商</h3>
        <p className="settings-group-hint">
          用于 generate_image 工具。列表顺序即优先级；超时/限流等会冷却并切换下一条。同一厂家可添加多条以配置不同模型。
        </p>
      </header>
      <div className="settings-chain-list">
        {providers.map((p, i) => {
          const st = cooldown[p.id];
          const cooling = Boolean(st && !st.available && !st.disabled);
          const disabled = Boolean(st?.disabled);
          const title =
            p.model.trim() !== ""
              ? `${labelOf(p.provider)} · ${p.model.trim()}`
              : labelOf(p.provider);
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
                  <span className="settings-search-provider-name" title={p.id}>
                    {title}
                  </span>
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
              <label className="settings-field">
                <span>Base URL（可选）</span>
                <input
                  type="text"
                  autoComplete="off"
                  value={p.base_url}
                  onChange={(e) => updateAt(i, { base_url: e.target.value })}
                  disabled={saving}
                  placeholder="留空用默认根；勿贴完整 /generation 路径"
                />
              </label>
              <label className="settings-field">
                <span>模型（可选）</span>
                <input
                  type="text"
                  autoComplete="off"
                  value={p.model}
                  onChange={(e) => updateAt(i, { model: e.target.value })}
                  disabled={saving}
                  placeholder="如 dall-e-3 / glm-image / wan2.7-image-pro / qwen-image-3.0-pro"
                />
              </label>
              <ProviderCooldownBar
                status={st}
                saving={saving}
                onClear={() => onClearCooldown(p.id)}
              />
            </article>
          );
        })}
      </div>
      <div className="settings-search-add-row">
        <label className="settings-field settings-search-add-field">
          <span className="visually-hidden">添加生图提供商</span>
          <select
            value=""
            disabled={saving}
            onChange={(e) => {
              const v = e.target.value as ImageProviderId;
              if (v) addProvider(v);
            }}
          >
            <option value="" disabled>
              + 添加生图提供商
            </option>
            {IMAGE_PROVIDER_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
