import type { ChatMessage } from "../types/chat";
import { normalizeDocContext } from "./chatMessageFormat";

export const CONVERSATION_OUTLINE_MIN_ITEMS = 3;
export const CONVERSATION_OUTLINE_LABEL_MAX = 72;

function escapeAttrSelector(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

export type ConversationOutlineItem = {
  messageId: string;
  /** 1-based 展示序号 */
  index: number;
  label: string;
  fullText: string;
};

function hasUserPayload(m: ChatMessage): boolean {
  if (m.text?.trim()) return true;
  if (m.attachments?.length) return true;
  if (normalizeDocContext(m.doc_context).length) return true;
  return false;
}

/** 压缩空白并截断为单行大纲文案；无文本时返回空串。 */
export function formatOutlineLabel(
  text: string,
  maxLen = CONVERSATION_OUTLINE_LABEL_MAX,
): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= maxLen) return cleaned;
  return `${cleaned.slice(0, maxLen).trimEnd()}…`;
}

/** 从会话消息提取可导航的用户提问（旧→新）。 */
export function buildConversationOutline(
  msgs: ChatMessage[],
): ConversationOutlineItem[] {
  const items: ConversationOutlineItem[] = [];
  for (const m of msgs) {
    if (m.role !== "user" || !m.id || !hasUserPayload(m)) continue;
    const fullText = m.text?.replace(/\s+/g, " ").trim() ?? "";
    const label = formatOutlineLabel(fullText) || "（附件）";
    items.push({
      messageId: m.id,
      index: items.length + 1,
      label,
      fullText: fullText || label,
    });
  }
  return items;
}

/**
 * 根据滚动位置返回当前应高亮的提问下标（0-based）。
 * 取「顶边已进入视口上方阈值」的最后一条用户提问。
 */
export function getConversationOutlineActiveIndex(
  scrollRoot: HTMLElement | null,
  items: ConversationOutlineItem[],
  offsetPx = 48,
): number {
  if (!scrollRoot || items.length === 0) return -1;
  const threshold = scrollRoot.getBoundingClientRect().top + offsetPx;
  let active = -1;
  for (let i = 0; i < items.length; i++) {
    const el = scrollRoot.querySelector<HTMLElement>(
      `[data-message-id="${escapeAttrSelector(items[i].messageId)}"]`,
    );
    if (!el) continue;
    if (el.getBoundingClientRect().top <= threshold + 2) {
      active = i;
    } else {
      break;
    }
  }
  return active;
}

/** 将目标用户消息顶对齐到滚动容器（留边距）并闪烁确认。 */
export function scrollToUserQuestion(
  scrollRoot: HTMLElement | null,
  messageId: string,
  offsetPx = 12,
): boolean {
  if (!scrollRoot) return false;
  const el = scrollRoot.querySelector<HTMLElement>(
    `[data-message-id="${escapeAttrSelector(messageId)}"]`,
  );
  if (!el) return false;

  const cRect = scrollRoot.getBoundingClientRect();
  const eRect = el.getBoundingClientRect();
  const nextTop = scrollRoot.scrollTop + (eRect.top - cRect.top) - offsetPx;
  scrollRoot.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });

  el.classList.add("chat-message-jump-flash");
  window.setTimeout(() => el.classList.remove("chat-message-jump-flash"), 3000);
  return true;
}
