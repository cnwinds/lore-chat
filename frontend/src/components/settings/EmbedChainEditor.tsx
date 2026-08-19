import type { CooldownStatus } from "./settingsTypes";
import {
  SettingsCandidateFoldToggle,
  SettingsFoldSection,
  useSettingsItemFold,
} from "./SettingsFold";
import { ProviderApiKeyLabel } from "./ProviderApiKeyLabel";
import { ModelNameField } from "./CandidateChainEditor";
import {
  EMBED_PROVIDER_DEFAULT_BASE_URL,
  EMBED_PROVIDER_OPTIONS,
  embedCandidateFromProvider,
  embedProviderLabel,
  type EmbedCandidateDraft,
  type EmbedProviderPresetId,
} from "./providerPresets";

type EmbedChainEditorProps = {
  candidates: EmbedCandidateDraft[];
  onChange: (next: EmbedCandidateDraft[]) => void;
  cooldown: CooldownStatus;
  onClearCooldown: (candidateId: string) => void;
  saving: boolean;
  attention?: boolean;
  hydrated?: boolean;
};

export function EmbedChainEditor({
  candidates,
  onChange,
  cooldown,
  onClearCooldown,
  saving,
  attention = false,
  hydrated = true,
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
      defaultOpen={hydrated && (candidates.length === 0 || attention)}
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

