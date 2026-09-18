// 生产环境经 nginx 同源代理时 VITE_API_BASE 留空；本地开发在 .env 中设为 http://localhost:8000

import type {
  ActiveTurnStatus,
  ChatMessage,
  ChatResult,
  ChatStreamEvent,
  Conversation,
  ConversationSummary,
  DocContextItem,
  IngestResult,
  Question,
  RoleSummary,
  RoomStatus,
  RoomSummary,
} from "./types/chat";
import {
  apiBase,
  openJson as apiFetch,
  openSse,
  readSseResponse,
  type ApiError,
  type PathExistsDetail,
  type PackPathChoiceDetail,
} from "./lib/httpTransport";
import { messageFromImportErrorBody } from "./utils/importKbError";
import type { ScheduleTiming } from "./utils/scheduleTiming";

export type { ApiError, PathExistsDetail, PackPathChoiceDetail, ActiveTurnStatus };

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

export type ProductChannel = "release" | "development";

export type ProductVersion = {
  version: string;
  revision: string | null;
  commits_ahead: number;
  channel: ProductChannel;
  display: string;
};

export type HealthStatus = {
  status: string;
  product?: ProductVersion;
  capabilities?: Record<string, unknown>;
};

export function getHealth() {
  return apiFetch<HealthStatus>("/api/health");
}

export function getSettings() {
  return apiFetch<Record<string, unknown>>("/api/admin/settings");
}

export type SettingsAttention = {
  any: boolean;
  model: {
    any: boolean;
    chat: boolean;
    utility: boolean;
    embed: boolean;
  };
  memory: {
    any: boolean;
    pending_count: number;
  };
  usage: {
    any: boolean;
    incomplete_price_count: number;
  };
};

export function getSettingsAttention() {
  return apiFetch<{ ok: boolean; attention: SettingsAttention }>(
    "/api/admin/settings-attention",
  );
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

export function clearImageCooldown(body: {
  provider_id?: string;
  candidate_id?: string;
  all?: boolean;
}) {
  return apiFetch<{ ok: boolean; image_cooldown: Record<string, unknown> }>(
    "/api/admin/image-cooldown/clear",
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
  video?: boolean;
  thinking: boolean;
  effort: string;
  effort_options: string[];
  image_wire: "data" | "url";
  video_wire?: "data" | "url";
  max_videos?: number;
  max_images?: number | null;
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
    refreshing?: boolean;
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

/** 单模型能力：与后端 lookup_capabilities / settings enrich 同源。 */
export type ModelCapabilitiesResponse = {
  ok: boolean;
  model: string;
  image: boolean;
  video?: boolean;
  thinking: boolean;
  effort: string;
  effort_options: string[];
  image_wire: "data" | "url";
  video_wire?: "data" | "url";
  max_videos?: number;
  max_images?: number | null;
  thinking_protocol: string;
  source?: string;
};

export function lookupModelCapabilities(model: string, baseUrl?: string) {
  const params = new URLSearchParams();
  params.set("model", model.trim());
  const bu = (baseUrl || "").trim();
  if (bu) params.set("base_url", bu);
  return apiFetch<ModelCapabilitiesResponse>(
    `/api/admin/model-capabilities?${params.toString()}`,
  );
}

export type ProviderModelsResponse = {
  ok: boolean;
  source: "provider" | "catalog_fallback" | string;
  error?: string | null;
  items: ModelCatalogItem[];
};

/** 按候选 Base URL / Key 拉远端 /models；失败时后端回退已知目录。 */
export function listProviderModels(body: {
  base_url: string;
  api_key?: string | null;
  candidate_id?: string | null;
  q?: string;
  kind?: "all" | "llm" | "embedding" | "image";
  limit?: number;
}) {
  return apiFetch<ProviderModelsResponse>("/api/admin/provider-models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  channel_instance_id?: string;
}) {
  const q = new URLSearchParams();
  if (params?.granularity) q.set("granularity", params.granularity);
  if (params?.start) q.set("start", params.start);
  if (params?.end) q.set("end", params.end);
  if (params?.channel_instance_id) {
    q.set("channel_instance_id", params.channel_instance_id);
  }
  const qs = q.toString();
  return apiFetch<UsageSummary>(`/api/usage/summary${qs ? `?${qs}` : ""}`);
}

export function getUsageEvents(params?: {
  start?: string;
  end?: string;
  model?: string;
  limit?: number;
  offset?: number;
  channel_instance_id?: string;
}) {
  const q = new URLSearchParams();
  if (params?.start) q.set("start", params.start);
  if (params?.end) q.set("end", params.end);
  if (params?.model) q.set("model", params.model);
  if (params?.limit != null) q.set("limit", String(params.limit));
  if (params?.offset != null) q.set("offset", String(params.offset));
  if (params?.channel_instance_id) {
    q.set("channel_instance_id", params.channel_instance_id);
  }
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

export { IMPORT_ERROR_BY_CODE, messageFromImportErrorBody } from "./utils/importKbError";

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
      const body: unknown = await r.json();
      detail = messageFromImportErrorBody(body) || detail;
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
  RoleSummary,
  RoomSummary,
  RoomParticipant,
  RoomStatus,
  GroupAssignmentStatus,
} from "./types/chat";
export { KB_MUTATING_TOOLS } from "./types/chat";
export {
  normalizeDocContext,
  getMessageCopyText,
  formatDuration,
  compactTokenCount,
  exactTokenCount,
  getMessageTokenUsage,
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
  roleId?: string | null;
  activeDocPaths?: string[];
  docContext?: DocContextItem[];
  primaryDocPath?: string | null;
  webEnabled?: boolean;
  attachments?: string[];
  /** 幂等重试键：同一 (conversation_id, clientMessageId) 重复发送不会重跑 Agent。 */
  clientMessageId?: string;
  /** 原地重新回复：复用已有用户消息 id，不追加重复提问 */
  reuseUserMessageId?: string;
  mentions?: string[];
  signal?: AbortSignal;
};

export async function* chatStream(
  text: string,
  options: ChatStreamOptions = {},
): AsyncGenerator<ChatStreamEvent> {
  const {
    conversationId,
    roleId,
    activeDocPaths = [],
    docContext,
    primaryDocPath,
    webEnabled = false,
    attachments = [],
    clientMessageId,
    reuseUserMessageId,
    mentions,
    signal,
  } = options;
  const body: Record<string, unknown> = {
    text,
    conversation_id: conversationId ?? undefined,
    role_id: roleId ?? undefined,
    client_message_id: clientMessageId ?? undefined,
    primary_doc_path: primaryDocPath ?? undefined,
    web_enabled: webEnabled,
    attachments: attachments.length ? attachments : undefined,
    mentions: mentions?.length ? mentions : undefined,
  };
  if (reuseUserMessageId) {
    body.reuse_user_message_id = reuseUserMessageId;
  }
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

/** 在指定会话开一轮但不跟当前视图流式。断开观测不取消执行。 */
export async function beginChatTurn(
  text: string,
  options: ChatStreamOptions = {},
): Promise<void> {
  const ac = new AbortController();
  const gen = chatStream(text, { ...options, signal: ac.signal });
  try {
    await gen.next();
  } finally {
    ac.abort();
  }
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
 * 产品 UI 请用 {@link chatStream}；同步 JSON，语义等价于 Agent 必须 write_doc。
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
 * 产品 UI 请用 {@link chatStream}；硬门禁止 write_doc，返回最终正文与 sources。
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
  destRoot?: string,
) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("directory", directory);
  if (filename) fd.append("filename", filename);
  if (destRoot) fd.append("dest_root", destRoot);
  return apiFetch<{
    rel_path: string;
    kind: string;
    indexed: boolean;
    files?: string[];
  }>("/api/kb/import", { method: "POST", body: fd });
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

export async function getEnabledSkills() {
  return apiFetch<{ roots: string[] }>("/api/enabled-skills");
}

export async function putEnabledSkills(roots: string[]) {
  return apiFetch<{ roots: string[] }>("/api/enabled-skills", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ roots }),
  });
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
  body: {
    choice?: string;
    choices?: string[];
    conversation_id?: string;
    inputs?: Record<string, string>;
  },
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

export async function listConversations(opts?: { roleId?: string }) {
  const qs = opts?.roleId
    ? `?role_id=${encodeURIComponent(opts.roleId)}`
    : "";
  return apiFetch<{ conversations: ConversationSummary[] }>(
    `/api/conversations${qs}`,
  );
}

export async function createConversation(opts?: {
  roleId?: string;
  title?: string;
}) {
  const body: Record<string, string> = {};
  if (opts?.roleId) body.role_id = opts.roleId;
  if (opts?.title) body.title = opts.title;
  return apiFetch<{ id: string; role_id?: string }>("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function listRoles() {
  return apiFetch<{ roles: RoleSummary[] }>("/api/roles");
}

export async function listRooms(kind: "group" = "group") {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  return apiFetch<{ rooms: RoomSummary[] }>(`/api/rooms?${params.toString()}`);
}

export async function createRoom(body: {
  title: string;
  role_ids: string[];
  avatar?: string | null;
}) {
  return apiFetch<RoomSummary>("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function updateRoom(
  id: string,
  body: { title?: string; role_ids?: string[]; avatar?: string | null },
) {
  return apiFetch<RoomSummary>(`/api/rooms/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteRoom(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/rooms/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function getRoom(id: string) {
  return apiFetch<RoomSummary & { messages?: ChatMessage[] }>(
    `/api/rooms/${encodeURIComponent(id)}`,
  );
}

export async function getRoomStatus(id: string) {
  return apiFetch<RoomStatus>(`/api/rooms/${encodeURIComponent(id)}/status`);
}

export async function postRoomMessage(
  id: string,
  body: { text: string; mentions?: string[]; client_message_id?: string },
) {
  return apiFetch<{
    room_id: string;
    message_id?: string;
    wake_status: string;
    turn_id?: string | null;
    target_role_id?: string | null;
    summary: string;
  }>(`/api/rooms/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** 与 RoleSummary 同义，供角色栏组件使用 */
export type Role = RoleSummary;

export async function getRole(roleId: string) {
  return apiFetch<RoleSummary>(
    `/api/roles/${encodeURIComponent(roleId)}`,
  );
}

export async function createRole(body: {
  name: string;
  system_prompt?: string;
  avatar?: string | null;
}) {
  return apiFetch<RoleSummary>("/api/roles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function ensureRoleActive(roleId: string) {
  return apiFetch<{
    conversation_id: string;
    role_id: string;
    created?: boolean;
  }>(`/api/roles/${encodeURIComponent(roleId)}/ensure-active`, {
    method: "POST",
  });
}

/** 三栏布局分支命名别名 */
export const ensureActiveConversation = ensureRoleActive;

export type RoleTimelineSegment = ConversationSummary & {
  messages?: ChatMessage[];
  active_turn?: Conversation["active_turn"];
  older_message_count?: number;
};

export type RoleTimeline = {
  role_id: string;
  tip_conversation_id: string;
  tip_created?: boolean;
  continuity_idle_hours: number;
  segments: RoleTimelineSegment[];
  has_more?: boolean;
  limit?: number;
};

export async function getRoleTimeline(
  roleId: string,
  opts?: {
    includeMessages?: boolean;
    limit?: number;
    beforeCreatedAt?: string;
    beforeId?: string;
    messageLimit?: number;
  },
) {
  const params = new URLSearchParams();
  if (opts?.includeMessages === false) {
    params.set("include_messages", "false");
  }
  if (opts?.limit !== undefined) {
    params.set("limit", String(opts.limit));
  }
  if (opts?.beforeCreatedAt) {
    params.set("before_created_at", opts.beforeCreatedAt);
  }
  if (opts?.beforeId) {
    params.set("before_id", opts.beforeId);
  }
  if (opts?.messageLimit !== undefined) {
    params.set("message_limit", String(opts.messageLimit));
  }
  const q = params.toString();
  return apiFetch<RoleTimeline>(
    `/api/roles/${encodeURIComponent(roleId)}/timeline${q ? `?${q}` : ""}`,
  );
}

export async function openRoleNewTopic(roleId: string) {
  return apiFetch<{ conversation_id: string; role_id: string }>(
    `/api/roles/${encodeURIComponent(roleId)}/new-topic`,
    { method: "POST" },
  );
}

export async function updateRole(
  roleId: string,
  body: {
    name?: string;
    system_prompt?: string;
    avatar?: string | null;
  },
) {
  return apiFetch<RoleSummary>(
    `/api/roles/${encodeURIComponent(roleId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function deleteRole(roleId: string) {
  return apiFetch<{ ok: boolean; deleted_conversations?: number }>(
    `/api/roles/${encodeURIComponent(roleId)}`,
    { method: "DELETE" },
  );
}

export async function listBusyRoles() {
  return apiFetch<{ role_ids: string[] }>("/api/roles/busy");
}

export type RoleSchedule = {
  id: string;
  role_id: string;
  prompt: string;
  interval_hours: number;
  kind?: string;
  timing?: ScheduleTiming;
  timing_summary?: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};

export async function listRoleSchedules(roleId: string) {
  return apiFetch<{ schedules: RoleSchedule[] }>(
    `/api/roles/${encodeURIComponent(roleId)}/schedules`,
  );
}

export async function createRoleSchedule(
  roleId: string,
  body: {
    prompt: string;
    timing?: ScheduleTiming;
    interval_hours?: number;
    enabled?: boolean;
  },
) {
  return apiFetch<RoleSchedule>(
    `/api/roles/${encodeURIComponent(roleId)}/schedules`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function updateRoleSchedule(
  roleId: string,
  scheduleId: string,
  body: {
    prompt?: string;
    timing?: ScheduleTiming;
    interval_hours?: number;
    enabled?: boolean;
  },
) {
  return apiFetch<RoleSchedule>(
    `/api/roles/${encodeURIComponent(roleId)}/schedules/${encodeURIComponent(scheduleId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function deleteRoleSchedule(roleId: string, scheduleId: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/roles/${encodeURIComponent(roleId)}/schedules/${encodeURIComponent(scheduleId)}`,
    { method: "DELETE" },
  );
}

export type RoleScheduleRun = {
  turn_id: string;
  conversation_id: string;
  status: string;
  started_at: string;
  finalized_at: string | null;
  summary: string;
};

export async function listRoleScheduleRuns(roleId: string, scheduleId: string) {
  return apiFetch<{ runs: RoleScheduleRun[] }>(
    `/api/roles/${encodeURIComponent(roleId)}/schedules/${encodeURIComponent(scheduleId)}/runs`,
  );
}

export type ConversationSearchHit = {
  kind?: "message" | "role" | "file" | "group";
  conversation_id: string;
  message_id: string | null;
  role_id: string;
  role_name?: string;
  role_avatar?: string | null;
  message_role?: string;
  path?: string;
  title: string;
  snippet: string;
  ts?: string | null;
};

export type WorkspaceSearchScope = "all" | "messages" | "roles" | "files";

export async function searchConversations(opts: {
  q: string;
  k?: number;
  roleId?: string;
  scope?: WorkspaceSearchScope;
}) {
  const params = new URLSearchParams();
  params.set("q", opts.q);
  if (opts.k !== undefined) params.set("k", String(opts.k));
  if (opts.roleId) params.set("role_id", opts.roleId);
  if (opts.scope) params.set("scope", opts.scope);
  return apiFetch<{ hits: ConversationSearchHit[]; tier: string }>(
    `/api/conversations/search?${params.toString()}`,
  );
}

export async function getConversation(
  id: string,
  opts?: { tail?: number; aroundId?: string; radius?: number },
) {
  const params = new URLSearchParams();
  if (opts?.aroundId) params.set("around_id", opts.aroundId);
  else if (opts?.tail) params.set("tail", String(opts.tail));
  if (opts?.aroundId && opts.radius !== undefined) {
    params.set("radius", String(opts.radius));
  }
  const q = params.toString();
  return apiFetch<Conversation>(
    `/api/conversations/${encodeURIComponent(id)}${q ? `?${q}` : ""}`,
  );
}

export async function getConversationMessages(
  id: string,
  opts: { beforeId: string; limit?: number },
) {
  const params = new URLSearchParams();
  params.set("before_id", opts.beforeId);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  return apiFetch<{ messages: ChatMessage[]; older_message_count: number }>(
    `/api/conversations/${encodeURIComponent(id)}/messages?${params.toString()}`,
  );
}

export async function getActiveTurnStatus(conversationId: string) {
  return apiFetch<ActiveTurnStatus>(
    `/api/conversations/${encodeURIComponent(conversationId)}/turns/active`,
  );
}

export type ContextStatsSegment = {
  key: string;
  label: string;
  tokens: number;
};

export type ContextStats = {
  model: string | null;
  context: { used_tokens: number | null; limit_tokens: number | null };
  segments: ContextStatsSegment[];
  cache_hit_rate: number | null;
  tool_calls: number;
  cost_total: number | null;
  turns_with_usage: number;
};

export function getContextStats(conversationId: string) {
  return apiFetch<ContextStats>(
    `/api/conversations/${encodeURIComponent(conversationId)}/context-stats`,
  );
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
