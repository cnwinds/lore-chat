/** 服务端发送队列客户端（排队以服务端记录为准，跨端延续）。 */

import { openJson } from "../lib/httpTransport";

export type QueueTiming = "inject" | "defer";

export type ServerSendQueueItem = {
  id: string;
  text: string;
  timing: QueueTiming;
  doc_context?: unknown[] | null;
  primary_doc?: string | null;
  attachments?: string[] | null;
  web_enabled: boolean;
  mentions?: string[] | null;
  status: string;
  error: string | null;
  created_at: string;
};

export type SendQueueSnapshot = {
  items: ServerSendQueueItem[];
  paused: boolean;
};

export type EnqueueBody = {
  text: string;
  timing?: QueueTiming;
  doc_context?: unknown;
  primary_doc?: string;
  attachments?: string[];
  web_enabled?: boolean;
  mentions?: string[];
};

export function getContextSendQueue(conversationId: string) {
  return openJson<SendQueueSnapshot>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue`,
  );
}

export function enqueueContextQueue(
  conversationId: string,
  body: EnqueueBody,
) {
  return openJson<{ item: ServerSendQueueItem }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
}

export function patchContextQueueItem(
  conversationId: string,
  itemId: string,
  patch: { text?: string; timing?: QueueTiming },
) {
  return openJson<{ item: ServerSendQueueItem }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue/${encodeURIComponent(itemId)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) },
  );
}

export function guideContextQueueItem(conversationId: string, itemId: string) {
  return openJson<{ item: ServerSendQueueItem }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue/${encodeURIComponent(itemId)}/guide`,
    { method: "POST" },
  );
}

export function moveContextQueueItem(
  conversationId: string,
  itemId: string,
  direction: -1 | 1,
) {
  return openJson<{ ok: boolean }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue/${encodeURIComponent(itemId)}/move`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ direction }) },
  );
}

export function removeContextQueueItem(conversationId: string, itemId: string) {
  return openJson<{ ok: boolean }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue/${encodeURIComponent(itemId)}`,
    { method: "DELETE" },
  );
}

export function clearContextQueue(conversationId: string) {
  return openJson<{ ok: boolean }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue`,
    { method: "DELETE" },
  );
}

export function pauseContextQueue(conversationId: string, paused: boolean) {
  return openJson<{ paused: boolean }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/queue/pause`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paused }) },
  );
}
