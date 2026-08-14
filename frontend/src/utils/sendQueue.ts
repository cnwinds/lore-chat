import type { DocContextItem } from "../api";

export type QueueTiming = "defer" | "inject";

export type SendQueueItem = {
  id: string;
  text: string;
  timing: QueueTiming;
  /** Merge with the next item into one outbound message when timings match. */
  mergeWithNext: boolean;
  doc_context?: DocContextItem[];
  primary_doc?: string | null;
  attachments?: string[];
  webEnabled: boolean;
  /** 原地重新回复：复用已有用户消息 */
  reuseUserMessageId?: string;
  replaceAssistantIndex?: number;
  /** Locked while inject submitted to backend for current turn. */
  locked?: boolean;
  error?: string | null;
};

export const SEND_QUEUE_MAX = 20;
export const SEND_QUEUE_STORAGE_PREFIX = "lorechat.sendQueue.v1.";

export function queueStorageKey(conversationId: string): string {
  return `${SEND_QUEUE_STORAGE_PREFIX}${conversationId}`;
}

export function loadSendQueue(conversationId: string | null): SendQueueItem[] {
  if (!conversationId || typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(queueStorageKey(conversationId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x): x is SendQueueItem => x && typeof x === "object" && typeof x.id === "string")
      .map((x) => ({
        id: x.id,
        text: typeof x.text === "string" ? x.text : "",
        timing: x.timing === "inject" ? "inject" : "defer",
        mergeWithNext: !!x.mergeWithNext,
        doc_context: Array.isArray(x.doc_context) ? x.doc_context : undefined,
        primary_doc: x.primary_doc ?? null,
        attachments: Array.isArray(x.attachments) ? x.attachments : undefined,
        webEnabled: !!x.webEnabled,
        reuseUserMessageId:
          typeof x.reuseUserMessageId === "string"
            ? x.reuseUserMessageId
            : undefined,
        replaceAssistantIndex:
          typeof x.replaceAssistantIndex === "number"
            ? x.replaceAssistantIndex
            : undefined,
        locked: false,
        error: null,
      }));
  } catch {
    return [];
  }
}

export function saveSendQueue(
  conversationId: string | null,
  items: SendQueueItem[],
): void {
  if (!conversationId || typeof localStorage === "undefined") return;
  try {
    const persistable = items.map(
      ({
        id,
        text,
        timing,
        mergeWithNext,
        doc_context,
        primary_doc,
        attachments,
        webEnabled,
        reuseUserMessageId,
        replaceAssistantIndex,
      }) => ({
        id,
        text,
        timing,
        mergeWithNext,
        doc_context,
        primary_doc,
        attachments,
        webEnabled,
        reuseUserMessageId,
        replaceAssistantIndex,
      }),
    );
    localStorage.setItem(
      queueStorageKey(conversationId),
      JSON.stringify(persistable),
    );
  } catch {
    /* ignore quota */
  }
}

/** Peel the next outbound group from the front (merge chain with same timing). */
export function takeNextGroup(items: SendQueueItem[]): {
  group: SendQueueItem[];
  rest: SendQueueItem[];
} | null {
  if (!items.length) return null;
  const first = items[0];
  const group: SendQueueItem[] = [first];
  let i = 0;
  while (i < items.length - 1 && items[i].mergeWithNext) {
    const next = items[i + 1];
    if (next.timing !== first.timing) break;
    group.push(next);
    i += 1;
  }
  return { group, rest: items.slice(group.length) };
}

export function mergeGroupText(group: SendQueueItem[]): string {
  return group.map((g) => g.text.trim()).filter(Boolean).join("\n\n");
}

export function setGroupTiming(
  items: SendQueueItem[],
  startIndex: number,
  timing: QueueTiming,
): SendQueueItem[] {
  const next = items.map((x) => ({ ...x }));
  let i = startIndex;
  while (i > 0 && next[i - 1].mergeWithNext) {
    i -= 1;
  }
  while (i < next.length) {
    next[i] = { ...next[i], timing, error: null };
    if (!next[i].mergeWithNext) break;
    i += 1;
  }
  return next;
}

export function moveQueueItem(
  items: SendQueueItem[],
  index: number,
  direction: -1 | 1,
): SendQueueItem[] {
  const j = index + direction;
  if (index < 0 || j < 0 || index >= items.length || j >= items.length) {
    return items;
  }
  const next = [...items];
  [next[index], next[j]] = [next[j], next[index]];
  return next;
}
