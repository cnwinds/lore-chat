import type { CooldownStatus } from "./settingsTypes";

type EntryStatus = CooldownStatus[string];

type Props = {
  status: EntryStatus | undefined;
  saving: boolean;
  onClear: () => void;
};

/** 搜索/生图提供商链共用的冷却/禁用条。 */
export function ProviderCooldownBar({ status, saving, onClear }: Props) {
  if (!status || (status.available && !status.disabled)) return null;
  const disabled = Boolean(status.disabled);
  return (
    <div
      className={`settings-health-bar${disabled ? " settings-health-bar--danger" : " settings-health-bar--warn"}`}
    >
      <span className="settings-health-dot" aria-hidden />
      <span className="settings-health-text">
        {disabled
          ? `已禁用${status.last_error ? ` · ${status.last_error}` : ""}`
          : `冷却中 · ${status.cooldown_remaining_sec ?? 0}s`}
      </span>
      <button
        type="button"
        className="settings-btn settings-btn--compact settings-btn--secondary"
        disabled={saving}
        onClick={onClear}
      >
        立即重试
      </button>
    </div>
  );
}
