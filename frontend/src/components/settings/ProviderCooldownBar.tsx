import type { CooldownStatus } from "./settingsTypes";
import { SettingsHealthBar } from "./SettingsHealthBar";

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
    <SettingsHealthBar
      tone={disabled ? "danger" : "warn"}
      summary={
        disabled
          ? `已禁用${status.last_error ? ` · ${status.last_error}` : ""}`
          : `冷却中 · ${status.cooldown_remaining_sec ?? 0}s`
      }
      detail={status.last_error}
      retryDisabled={saving}
      onRetry={onClear}
    />
  );
}
