/** 工作区搜索面板：命中项身份与全局快捷键。 */

export function workspaceSearchHitKey(hit: {
  kind?: string | null;
  conversation_id?: string | null;
  message_id?: string | null;
  role_id?: string | null;
  path?: string | null;
}): string {
  const kind = hit.kind || "message";
  return `${kind}:${hit.conversation_id || ""}:${hit.message_id || ""}:${hit.role_id || ""}:${hit.path || ""}`;
}

export function workspaceSearchHotkeyLabel(
  userAgent = typeof navigator !== "undefined" ? navigator.userAgent : "",
): string {
  return /mac|iphone|ipad|ipod/i.test(userAgent) ? "⌘K" : "Ctrl+K";
}

export function isWorkspaceSearchHotkey(event: {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  isComposing?: boolean;
  repeat?: boolean;
}): boolean {
  if (event.isComposing || event.repeat) return false;
  if (event.altKey || event.shiftKey) return false;
  if (!(event.metaKey || event.ctrlKey)) return false;
  return event.key.toLowerCase() === "k";
}
