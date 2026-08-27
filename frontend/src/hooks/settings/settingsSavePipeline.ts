import { notifySettingsChanged } from "../../utils/settingsChangedEvent";
import { maybeEnableComposerWebSearch } from "../../utils/webSearchPreference";

/** 保存设置后的显式副作用链（不混在 load 路径）。 */
export function runSettingsSaveSideEffects(opts: {
  wasSearchConfigured: boolean;
  nowSearchConfigured: boolean;
}): void {
  notifySettingsChanged();
  maybeEnableComposerWebSearch(
    opts.wasSearchConfigured,
    opts.nowSearchConfigured,
  );
}
