export type SettingsTab =
  | "model"
  | "search"
  | "agent"
  | "kb"
  | "usage"
  | "account"
  | "share";

export const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: "model", label: "模型" },
  { id: "search", label: "检索" },
  { id: "agent", label: "Agent" },
  { id: "kb", label: "知识库" },
  { id: "share", label: "分享" },
  { id: "usage", label: "用量" },
  { id: "account", label: "账户" },
];

const SETTINGS_TAB_STORAGE_KEY = "lorechat.settingsTab";
const SETTINGS_TAB_IDS = new Set<string>(SETTINGS_TABS.map((t) => t.id));

export function readStoredSettingsTab(): SettingsTab {
  try {
    const stored = localStorage.getItem(SETTINGS_TAB_STORAGE_KEY);
    if (stored && SETTINGS_TAB_IDS.has(stored)) return stored as SettingsTab;
  } catch {
    /* ignore */
  }
  return "model";
}

export function writeStoredSettingsTab(tab: SettingsTab) {
  try {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, tab);
  } catch {
    /* ignore */
  }
}
