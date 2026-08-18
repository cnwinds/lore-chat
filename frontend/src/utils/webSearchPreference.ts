/** 聊天框「联网搜索」开关：localStorage + 跨组件通知。 */

export const WEB_SEARCH_STORAGE_KEY = "lorechat.webSearch";
export const WEB_SEARCH_CHANGED_EVENT = "lorechat:web-search-changed";

export function readWebSearchEnabled(): boolean {
  if (typeof localStorage === "undefined") return false;
  return localStorage.getItem(WEB_SEARCH_STORAGE_KEY) === "1";
}

export function writeWebSearchEnabled(on: boolean): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(WEB_SEARCH_STORAGE_KEY, on ? "1" : "0");
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(WEB_SEARCH_CHANGED_EVENT, { detail: { enabled: on } }),
    );
  }
}

/**
 * 搜索从「未配置」变为「至少一家有 Key」时打开聊天框联网搜索。
 * 已配置后再改 Key / 用户手动关掉，不再强行打开。
 */
export function maybeEnableComposerWebSearch(
  wasConfigured: boolean,
  nowConfigured: boolean,
): boolean {
  if (wasConfigured || !nowConfigured) return false;
  writeWebSearchEnabled(true);
  return true;
}
