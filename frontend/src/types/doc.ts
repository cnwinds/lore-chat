export type DocWidth = "narrow" | "wide";
export type DocMode = "panel" | "float" | "page";
export type DocPane = "float" | "pinned";
export type EditMode = "preview" | "markdown";
export type UnsavedPrompt = "view" | "close" | "navigate" | "reload";

/** refreshKb 可选参数：本地保存时跳过本栏，避免 remount 丢滚动/光标 */
export type RefreshKbOpts = { except?: DocPane };
export type RefreshKb = (changedPath?: string, opts?: RefreshKbOpts) => void;
