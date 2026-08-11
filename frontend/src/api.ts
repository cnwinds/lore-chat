// 生产环境经 nginx 同源代理时 VITE_API_BASE 留空；本地开发在 .env 中设为 http://localhost:8000

import type {
  ChatMessage,
  ChatResult,
  ChatStreamEvent,
  Conversation,
  ConversationSummary,
  DocContextItem,
  IngestResult,
  Question,
} from "./types/chat";
import {
  apiBase,
  openJson as apiFetch,
  openSse,
  readSseResponse,
  type ApiError,
  type PathExistsDetail,
} from "./lib/httpTransport";

export type { ApiError, PathExistsDetail };

export type AuthStatus = {
  setup_required: boolean;
  authenticated: boolean;
};

export function getAuthStatus() {
  return apiFetch<AuthStatus>("/api/auth/status");
}

export function setupAuth(password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export function login(password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export function logout() {
  return apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function getSettings() {
  return apiFetch<Record<string, unknown>>("/api/admin/settings");
}

export function putSettings(patch: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/api/admin/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function clearModelCooldown(body: { candidate_id?: string; all?: boolean }) {
  return apiFetch<{ ok: boolean; model_cooldown: Record<string, unknown> }>(
    "/api/admin/model-cooldown/clear",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function clearSearchCooldown(body: {
  provider_id?: string;
  candidate_id?: string;
  all?: boolean;
}) {
  return apiFetch<{ ok: boolean; search_cooldown: Record<string, unknown> }>(
    "/api/admin/search-cooldown/clear",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export type ModelCatalogItem = {
  provider: string;
  id: string;
  name: string;
  image: boolean;
  thinking: boolean;
  effort: string;
  effort_options: string[];
  image_wire: "data" | "url";
  thinking_protocol: string;
  embedding?: boolean;
};

export type ModelCatalogResponse = {
  ok: boolean;
  source: string;
  status: {
    source?: string;
    fetched_at?: number;
    stale?: boolean;
    count?: number;
    error?: string | null;
  };
  items: ModelCatalogItem[];
};

export function searchModelCatalog(
  q: string,
  opts?: { limit?: number; refresh?: boolean; kind?: "all" | "llm" | "embedding" },
) {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.refresh) params.set("refresh", "1");
  if (opts?.kind && opts.kind !== "all") params.set("kind", opts.kind);
  const qs = params.toString();
  return apiFetch<ModelCatalogResponse>(
    `/api/admin/model-catalog${qs ? `?${qs}` : ""}`,
  );
}

export type UsageAgg = {
  calls: number;
  ok_calls: number;
  error_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cache_tokens?: number;
  unknown_token_calls: number;
  cost: number;
  cost_known_calls: number;
  unpriced_calls: number;
  model?: string;
  bucket?: string;
};

export type UsageSummary = {
  timezone: string;
  granularity: string;
  start: string;
  end: string;
  totals: UsageAgg;
  by_bucket: UsageAgg[];
  by_model: Array<UsageAgg & { model: string }>;
};

export type UsageEvent = {
  id: string;
  ts: string;
  model: string;
  kind: string;
  role?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  cache_tokens?: number | null;
  tokens_known: number | boolean;
  cost?: number | null;
  status: string;
  error?: string | null;
  duration_ms?: number | null;
  conversation_id?: string | null;
  turn_id?: string | null;
};

export type UsagePrice = {
  model: string;
  prompt_per_1m: number | null;
  completion_per_1m: number | null;
  cache_input_per_1m: number | null;
  embed_per_1m: number | null;
  kinds?: string[];
  updated_at: string;
};

export function getUsageSummary(params?: {
  granularity?: string;
  start?: string;
  end?: string;
}) {
  const q = new URLSearchParams();
  if (params?.granularity) q.set("granularity", params.granularity);
  if (params?.start) q.set("start", params.start);
  if (params?.end) q.set("end", params.end);
  const qs = q.toString();
  return apiFetch<UsageSummary>(`/api/usage/summary${qs ? `?${qs}` : ""}`);
}

export function getUsageEvents(params?: {
  start?: string;
  end?: string;
  model?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.start) q.set("start", params.start);
  if (params?.end) q.set("end", params.end);
  if (params?.model) q.set("model", params.model);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiFetch<{ items: UsageEvent[]; limit: number; offset: number }>(
    `/api/usage/events${qs ? `?${qs}` : ""}`,
  );
}

export function getUsagePrices() {
  return apiFetch<{ items: UsagePrice[] }>("/api/usage/prices");
}

export function putUsagePrice(body: {
  model: string;
  prompt_per_1m?: number | null;
  completion_per_1m?: number | null;
  cache_input_per_1m?: number | null;
  embed_per_1m?: number | null;
}) {
  return apiFetch<UsagePrice>("/api/usage/prices", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getUsagePrefs() {
  return apiFetch<{ timezone: string; retention_days: number }>("/api/usage/prefs");
}

export function putUsagePrefs(body: {
  timezone?: string;
  retention_days?: number;
}) {
  return apiFetch<{ timezone: string; retention_days: number }>("/api/usage/prefs", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function clearUsage() {
  return apiFetch<{ deleted: number }>("/api/usage/clear", { method: "POST" });
}

export function changePassword(old_password: string, new_password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password, new_password }),
  });
}

export async function downloadExport() {
  const r = await fetch(`${apiBase()}/api/admin/export`, { credentials: "include" });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : typeof body.message === "string"
            ? body.message
            : JSON.stringify(body);
    } catch {
      try {
        detail = (await r.text()) || detail;
      } catch {
        /* ignore */
      }
    }
    const err = new Error(detail || `导出失败 (${r.status})`) as ApiError;
    err.status = r.status;
    if (r.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw err;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "lorechat-kb.zip";
  a.click();
  URL.revokeObjectURL(url);
}

export type ImportKbResult = {
  ok: boolean;
  message: string;
  backup_path?: string;
};

export async function importKb(
  file: File,
  mode: "empty_only" | "overwrite",
): Promise<ImportKbResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode);
  const r = await fetch(`${apiBase()}/api/admin/import`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) {
    let detail = "导入失败";
    try {
      const body = await r.json();
      const d = body.detail;
      if (typeof d === "string") {
        detail = d;
      } else if (d && typeof d === "object" && typeof d.detail === "string") {
        detail = d.detail;
      } else if (typeof body.message === "string") {
        detail = body.message;
      }
    } catch {
      try {
        detail = (await r.text()) || detail;
      } catch {
        /* ignore */
      }
    }
    const err = new Error(detail || `导入失败 (${r.status})`) as ApiError;
    err.status = r.status;
    if (r.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw err;
  }
  return r.json() as Promise<ImportKbResult>;
}

export type ReindexResult = {
  ok: boolean;
  docs_indexed: number;
  conversations_fts: number;
  conversations_vector: number;
};

export function reindexKb() {
  return apiFetch<ReindexResult>("/api/admin/reindex", { method: "POST" });
}

export type {
  QuestionOption,
  Question,
  IngestResult,
  ChatRecallResult,
  ChatRememberResult,
  ChatResult,
  SourceRef,
  TimelineBlock,
  DocContextItem,
  ChatMessage,
  CumulativeInfo,
  ChatStreamEvent,
  ConversationSummary,
  Conversation,
} from "./types/chat";
export { KB_MUTATING_TOOLS } from "./types/chat";
export {
  normalizeDocContext,
  getMessageCopyText,
  formatDuration,
  computeCumulative,
  dedupeSources,
  titleFromText,
} from "./utils/chatMessageFormat";
export { TOOL_LABELS } from "./utils/toolLabels";
export { updateTimeline, mergeServerTimeline } from "./utils/timelineStream";

/** @deprecated Use {@link chatStream} — /api/chat returns SSE; product UI only. */
export async function chat(text: string, conversationId?: string | null) {
  return apiFetch<ChatResult>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      conversation_id: conversationId ?? undefined,
    }),
  });
}

export type ChatStreamOptions = {
  conversationId?: string | null;
  activeDocPaths?: string[];
  docContext?: DocContextItem[];
  primaryDocPath?: string | null;
  webEnabled?: boolean;
  attachments?: string[];
  /** 幂等重试键：同一 (conversation_id, clientMessageId) 重复发送不会重跑 Agent。 */
  clientMessageId?: string;
  signal?: AbortSignal;
};

export async function* chatStream(
  text: string,
  options: ChatStreamOptions = {},
): AsyncGenerator<ChatStreamEvent> {
  const {
    conversationId,
    activeDocPaths = [],
    docContext,
    primaryDocPath,
    webEnabled = false,
    attachments = [],
    clientMessageId,
    signal,
  } = options;
  const body: Record<string, unknown> = {
    text,
    conversation_id: conversationId ?? undefined,
    client_message_id: clientMessageId ?? undefined,
    primary_doc_path: primaryDocPath ?? undefined,
    web_enabled: webEnabled,
    attachments: attachments.length ? attachments : undefined,
  };
  if (docContext?.length) {
    body.doc_context = docContext;
  } else if (activeDocPaths.length) {
    body.active_doc_paths = activeDocPaths;
  }
  const r = await openSse("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  yield* readSseResponse(r);
}


export async function* observeActiveTurnStream(
  conversationId: string,
  options: { afterSeq?: number; signal?: AbortSignal } = {},
): AsyncGenerator<ChatStreamEvent> {
  const params = new URLSearchParams();
  if (options.afterSeq !== undefined) {
    params.set("after_seq", String(options.afterSeq));
  }
  const qs = params.toString();
  const r = await openSse(
    `/api/conversations/${encodeURIComponent(conversationId)}/turns/active/stream${qs ? `?${qs}` : ""}`,
    { method: "GET", signal: options.signal },
  );
  yield* readSseResponse(r);
}

export function stopChat(conversationId: string) {
  return apiFetch<{ status: string; conversation_id: string }>("/api/chat/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
}

export type ChatInjectBody = {
  conversationId: string;
  text: string;
  injectId: string;
  clientMessageId?: string;
  docContext?: DocContextItem[];
  primaryDocPath?: string | null;
  attachments?: string[];
};

export function chatInject(body: ChatInjectBody) {
  return apiFetch<{ status: string; inject_id: string }>("/api/chat/inject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: body.conversationId,
      text: body.text,
      inject_id: body.injectId,
      client_message_id: body.clientMessageId ?? `inject:${body.injectId}`,
      doc_context: body.docContext,
      primary_doc_path: body.primaryDocPath ?? undefined,
      attachments: body.attachments,
    }),
  });
}

/**
 * 强制落库（测试 / 脚本 API）。
 * 产品 UI 请用 {@link chatStream}；同步 JSON，语义等价于 Agent 必须 write_kb。
 * @see docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
 */
export async function ingest(text: string) {
  return apiFetch<IngestResult>("/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

/**
 * 只读问答（测试 / 脚本 API）。
 * 产品 UI 请用 {@link chatStream}；硬门禁止 write_kb，返回最终正文与 sources。
 * @see docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
 */
export async function ask(query: string) {
  return apiFetch<{ text: string; sources: string[]; attachments: string[] }>(
    "/api/ask",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    },
  );
}

export async function kbImport(
  file: File,
  directory: string,
  filename?: string,
) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("directory", directory);
  if (filename) fd.append("filename", filename);
  return apiFetch<{ rel_path: string; kind: string; indexed: boolean }>(
    "/api/kb/import",
    { method: "POST", body: fd },
  );
}

export async function kbMove(body: {
  from_path: string;
  to_directory: string;
  to_filename?: string;
}) {
  return apiFetch<{ rel_path: string; from_path: string }>("/api/kb/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function kbDelete(path: string) {
  return apiFetch<{ deleted_paths: string[] }>("/api/kb/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}

export { isMarkdownPath, parentDirectory } from "./utils/kbPath";

export async function getTree() {
  return apiFetch<{ docs: string[] }>("/api/tree");
}

export async function discoverSkills(fromDir = "") {
  const q = fromDir ? `?from_dir=${encodeURIComponent(fromDir)}` : "";
  return apiFetch<{ roots: string[] }>(`/api/kb/discover-skills${q}`);
}

export type DocContent = {
  rel_path: string;
  meta: Record<string, unknown>;
  body: string;
};

export async function getDoc(path: string) {
  return apiFetch<DocContent>(`/api/doc?path=${encodeURIComponent(path)}`);
}

export async function saveDoc(path: string, body: string) {
  return apiFetch<DocContent>("/api/doc", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, body }),
  });
}

export async function getQuestions() {
  return apiFetch<{ questions: Question[] }>("/api/questions");
}

export async function resolveQuestion(
  qid: string,
  body: { choice?: string; choices?: string[]; conversation_id?: string },
) {
  return apiFetch<IngestResult>(`/api/questions/${qid}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function downloadUrl(
  path: string,
  opts?: { download?: boolean },
) {
  const q = new URLSearchParams({ path });
  if (opts?.download) q.set("download", "1");
  return `${apiBase()}/api/download?${q.toString()}`;
}

export async function downloadKbDirectory(directory: string) {
  const r = await fetch(
    `${apiBase()}/api/download-zip?path=${encodeURIComponent(directory)}`,
    { credentials: "include" },
  );
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : typeof body.message === "string"
            ? body.message
            : JSON.stringify(body);
    } catch {
      try {
        detail = (await r.text()) || detail;
      } catch {
        /* ignore */
      }
    }
    const err = new Error(detail || `下载失败 (${r.status})`) as ApiError;
    err.status = r.status;
    if (r.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw err;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const base = directory.replace(/\/+$/, "").split("/").pop() || "folder";
  a.download = `${base}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function listConversations() {
  return apiFetch<{ conversations: ConversationSummary[] }>("/api/conversations");
}

export async function createConversation() {
  return apiFetch<{ id: string }>("/api/conversations", { method: "POST" });
}

export async function getConversation(id: string) {
  return apiFetch<Conversation>(`/api/conversations/${encodeURIComponent(id)}`);
}

export type ConversationSystemEvent = {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export async function getConversationEvents(
  conversationId: string,
  options?: { afterEventId?: string | null; limit?: number },
) {
  const params = new URLSearchParams();
  if (options?.afterEventId) params.set("after_event_id", options.afterEventId);
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  const qs = params.toString();
  return apiFetch<{ events: ConversationSystemEvent[] }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/events${qs ? `?${qs}` : ""}`,
  );
}

export async function appendConversationMessages(
  id: string,
  messages: ChatMessage[],
) {
  return apiFetch<Conversation>(`/api/conversations/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
}

export async function deleteConversation(id: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/conversations/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

/** 把整段会话通读后全局重构、去重、成文归档到知识库。 */
export async function summarizeConversation(
  id: string,
  location: { directory: string; filename: string },
) {
  return apiFetch<IngestResult>(
    `/api/conversations/${encodeURIComponent(id)}/summarize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(location),
    },
  );
}

export type MergeSession = {
  id: string;
  status: "pending_review" | "accepted" | "rejected";
  new_path: string;
  source_paths: string[];
  instruction?: string;
  order?: string[];
  user_modified: boolean;
};

export type MergeResult = {
  status: string;
  merge_id: string | null;
  rel_path: string | null;
  source_paths: string[];
  user_modified: boolean;
  question_id: string | null;
  message: string;
};

type MergeSessionResponse = {
  session: Omit<MergeSession, "user_modified">;
  user_modified: boolean;
};

function toMergeSession(data: MergeSessionResponse): MergeSession {
  return { ...data.session, user_modified: data.user_modified };
}

export async function mergeDocs({
  paths,
  instruction,
  order,
  title,
}: {
  paths: string[];
  instruction?: string;
  order?: string[];
  title?: string;
}): Promise<MergeResult> {
  return apiFetch<MergeResult>("/api/docs/merge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, instruction, order, title }),
  });
}

export async function getMergeSession(id: string): Promise<MergeSession> {
  const data = await apiFetch<MergeSessionResponse>(
    `/api/docs/merge/${encodeURIComponent(id)}`,
  );
  return toMergeSession(data);
}

export async function getActiveMerge(path: string): Promise<MergeSession | null> {
  const r = await fetch(
    `${apiBase()}/api/docs/merge/active?path=${encodeURIComponent(path)}`,
    { credentials: "include" },
  );
  if (r.status === 404) return null;
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : typeof body.message === "string"
            ? body.message
            : JSON.stringify(body);
    } catch {
      try {
        detail = (await r.text()) || detail;
      } catch {
        /* ignore */
      }
    }
    const err = new Error(detail || `请求失败 (${r.status})`) as ApiError;
    err.status = r.status;
    if (r.status === 401) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw err;
  }
  const data = (await r.json()) as MergeSessionResponse;
  return toMergeSession(data);
}

export async function regenerateMerge(id: string): Promise<MergeResult> {
  return apiFetch<MergeResult>(
    `/api/docs/merge/${encodeURIComponent(id)}/regenerate`,
    { method: "POST" },
  );
}

export async function acceptMerge(id: string): Promise<MergeResult> {
  return apiFetch<MergeResult>(
    `/api/docs/merge/${encodeURIComponent(id)}/accept`,
    { method: "POST" },
  );
}

export async function rejectMerge(id: string): Promise<MergeResult> {
  return apiFetch<MergeResult>(
    `/api/docs/merge/${encodeURIComponent(id)}/reject`,
    { method: "POST" },
  );
}

export async function resolveMergeSources(
  id: string,
  deletePaths: string[],
): Promise<MergeResult> {
  return apiFetch<MergeResult>(
    `/api/docs/merge/${encodeURIComponent(id)}/resolve-sources`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delete_paths: deletePaths }),
    },
  );
}

export type MemoryFact = {
  id: string;
  slot_key: string;
  statement: string;
  category?: string;
  origin?: string;
  status?: string;
  confidence?: number;
  conversation_ids: string[];
  updated_at?: string;
};

export function listMemoryFacts() {
  return apiFetch<{ facts: MemoryFact[]; count: number }>("/api/memory/facts");
}

export function confirmMemoryFact(factId: string) {
  return apiFetch<{ ok: boolean; message?: string }>(
    `/api/memory/facts/${encodeURIComponent(factId)}/confirm`,
    { method: "POST" },
  );
}

export function rejectMemoryFact(factId: string) {
  return apiFetch<{ ok: boolean; message?: string }>(
    `/api/memory/facts/${encodeURIComponent(factId)}/reject`,
    { method: "POST" },
  );
}

export function editMemoryFact(factId: string, statement: string) {
  return apiFetch<{ ok: boolean; message?: string }>(
    `/api/memory/facts/${encodeURIComponent(factId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ statement }),
    },
  );
}

export function forgetMemoryFact(factId: string) {
  return apiFetch<{ ok: boolean; message?: string }>(
    `/api/memory/facts/${encodeURIComponent(factId)}/forget`,
    { method: "POST" },
  );
}

