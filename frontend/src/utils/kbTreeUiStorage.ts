/** 知识库目录树 UI 状态（展开路径、滚动位置）持久化。 */

export const KB_TREE_UI_STORAGE_KEY = "lorechat.kbTreeUi.v1";

export type KbTreeUiState = {
  /** 缺省表示从未手动改过展开，加载时用默认展开规则 */
  expandedPaths?: string[];
  scrollTop?: number;
};

export function loadKbTreeUi(): KbTreeUiState | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(KB_TREE_UI_STORAGE_KEY);
    if (raw == null) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    const obj = parsed as Record<string, unknown>;
    const state: KbTreeUiState = {};
    if (Array.isArray(obj.expandedPaths)) {
      state.expandedPaths = obj.expandedPaths.filter(
        (p): p is string => typeof p === "string",
      );
    }
    if (typeof obj.scrollTop === "number" && Number.isFinite(obj.scrollTop)) {
      state.scrollTop = Math.max(0, obj.scrollTop);
    }
    return state;
  } catch {
    return null;
  }
}

function writeKbTreeUi(state: KbTreeUiState): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(KB_TREE_UI_STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore quota / private mode */
  }
}

/** 合并写入，保留另一字段已有值。 */
export function patchKbTreeUi(partial: KbTreeUiState): KbTreeUiState {
  const next: KbTreeUiState = { ...(loadKbTreeUi() ?? {}), ...partial };
  writeKbTreeUi(next);
  return next;
}

export function hasPersistedExpanded(): boolean {
  return loadKbTreeUi()?.expandedPaths != null;
}

export function saveKbTreeExpanded(expandedPaths: string[]): void {
  patchKbTreeUi({ expandedPaths: [...expandedPaths].sort() });
}

/** 仅在用户已持久化过展开状态时更新，避免把默认规则固化进 storage。 */
export function saveKbTreeExpandedIfPersisted(expandedPaths: string[]): void {
  if (!hasPersistedExpanded()) return;
  saveKbTreeExpanded(expandedPaths);
}

export function saveKbTreeScrollTop(scrollTop: number): void {
  patchKbTreeUi({ scrollTop: Math.max(0, scrollTop) });
}
