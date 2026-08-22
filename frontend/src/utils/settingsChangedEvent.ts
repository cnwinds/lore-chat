/** 设置保存后跨组件通知（聊天 Composer 能力提示等）。 */

export const SETTINGS_CHANGED_EVENT = "lorechat:settings-changed";

export function notifySettingsChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(SETTINGS_CHANGED_EVENT));
  }
}
