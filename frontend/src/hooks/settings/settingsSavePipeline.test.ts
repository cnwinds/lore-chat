import { describe, expect, it, vi } from "vitest";
import { runSettingsSaveSideEffects } from "./settingsSavePipeline";
import * as settingsChanged from "../../utils/settingsChangedEvent";
import * as webSearch from "../../utils/webSearchPreference";

describe("runSettingsSaveSideEffects", () => {
  it("notifies settings changed and may enable composer web search", () => {
    vi.spyOn(settingsChanged, "notifySettingsChanged").mockImplementation(() => {});
    vi.spyOn(webSearch, "maybeEnableComposerWebSearch").mockReturnValue(true);
    runSettingsSaveSideEffects({
      wasSearchConfigured: false,
      nowSearchConfigured: true,
    });
    expect(settingsChanged.notifySettingsChanged).toHaveBeenCalled();
    expect(webSearch.maybeEnableComposerWebSearch).toHaveBeenCalledWith(
      false,
      true,
    );
  });
});
