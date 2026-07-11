// 生产环境经 nginx 同源代理时 VITE_API_BASE 留空；本地开发在 .env 中设为 http://localhost:8000
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init);
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
    throw new Error(detail || `请求失败 (${r.status})`);
  }
  return r.json() as Promise<T>;
}

export type QuestionOption = { id: string; label: string };
export type Question = {
  id: string;
  question: string;
  options: QuestionOption[];
  multi_select?: boolean;
};

export type IngestResult = {
  status: "saved" | "question" | "continue" | "acknowledged" | string;
  rel_path: string | null;
  question_id: string | null;
  message: string;
  continue_prompt?: string | null;
};

export type ChatRecallResult = {
  intent: "recall";
  text: string;
  sources: string[];
  attachments: string[];
};

export type ChatRememberResult = IngestResult & { intent: "remember" };

export type ChatResult = ChatRecallResult | ChatRememberResult;

export type SourceRef =
  | { type: "kb"; path: string; excerpt?: string; line?: number }
  | { type: "web"; url: string; title: string; snippet: string }
  | {
      type: "search";
      provider: string;
      url: string;
      title: string;
      snippet: string;
    }
  | { type: "conversation"; cid: string; excerpt?: string };

function toolQueryFromInput(input: unknown): string | undefined {
  if (!input || typeof input !== "object" || !("query" in input)) return undefined;
  const q = (input as { query?: unknown }).query;
  return typeof q === "string" && q.trim() ? q.trim() : undefined;
}

export type TimelineBlock =
  | {
      type: "tool";
      id: string;
      tool: string;
      label: string;
      ts: string;
      status: "running" | "done";
      /** 检索/搜索关键词（search_kb、web_search） */
      query?: string;
      summary?: string;
      sources?: SourceRef[];
      content?: string;
      duration_ms?: number;
      question_id?: string;
      question?: string;
      options?: QuestionOption[];
      multi_select?: boolean;
      choice_resolved?: string;
    }
  | {
      type: "parallel";
      batch_id: string;
      ts: string;
      children: TimelineBlock[];
      duration_ms?: number;
    }
  | { type: "text"; ts: string; content: string };

export type ChatMessage = {
  role: "user" | "assistant";
  ts?: string;
  text?: string;
  timeline?: TimelineBlock[];
  sources?: SourceRef[];
  attachments?: string[];
  intent?: "recall" | "remember";
  /** 本轮回复总耗时（毫秒），来自 SSE done 事件 */
  total_duration_ms?: number;
};

/** 提取消息可复制文本；助手仅含 timeline 中的结论文字 */
export function getMessageCopyText(m: ChatMessage): string | null {
  if (m.role === "user") {
    const text = m.text?.trim();
    return text || null;
  }
  if (m.timeline?.length) {
    const parts = m.timeline
      .filter((b): b is Extract<TimelineBlock, { type: "text" }> => b.type === "text")
      .map((b) => b.content.trim())
      .filter(Boolean);
    if (parts.length) return parts.join("\n\n");
  }
  const text = m.text?.trim();
  return text || null;
}

/** 将毫秒格式化为可读耗时 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

export type CumulativeInfo = {
  toolCumulative: Map<string, number>;
  parallelCumulative: Map<string, number>;
};

/** 按时间线顺序计算各步骤完成时的累计耗时 */
export function computeCumulative(timeline: TimelineBlock[]): CumulativeInfo {
  const toolCumulative = new Map<string, number>();
  const parallelCumulative = new Map<string, number>();
  let cumulative = 0;

  for (const block of timeline) {
    if (block.type === "tool") {
      if (block.status === "done" && block.duration_ms !== undefined) {
        cumulative += block.duration_ms;
      }
      toolCumulative.set(block.id, cumulative);
    } else if (block.type === "parallel") {
      const batchStart = cumulative;
      for (const child of block.children) {
        if (child.type === "tool") {
          const afterBatch =
            block.duration_ms !== undefined
              ? batchStart + block.duration_ms
              : batchStart;
          toolCumulative.set(child.id, afterBatch);
        }
      }
      if (block.duration_ms !== undefined) {
        cumulative = batchStart + block.duration_ms;
      }
      parallelCumulative.set(block.batch_id, cumulative);
    }
  }

  return { toolCumulative, parallelCumulative };
}

/** 按 path/url 去重来源列表 */
export function dedupeSources(sources: SourceRef[]): SourceRef[] {
  const seen = new Set<string>();
  const out: SourceRef[] = [];
  for (const s of sources) {
    const key =
      s.type === "kb"
        ? `kb:${s.path}`
        : s.type === "conversation"
          ? `conv:${s.cid}`
          : `${s.type}:${s.url}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(s);
    }
  }
  return out;
}

export type ChatStreamEvent = { event: string; data: Record<string, unknown> };

export const TOOL_LABELS: Record<string, string> = {
  search_kb: "检索本地知识库",
  read_doc: "读取文档",
  fetch_url: "打开链接",
  web_search: "搜索网页",
  write_kb: "整理到知识库",
  ask_user: "征询用户",
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  summarized?: boolean;
  summary_path?: string | null;
};

/** 与后端 `_title_from_text` 对齐：取首行，最长 40 字。 */
export function titleFromText(text: string): string {
  const line = text.trim().split("\n")[0] ?? "";
  if (line.length > 40) return `${line.slice(0, 40)}…`;
  return line || "新对话";
}

export type Conversation = ConversationSummary & {
  messages: ChatMessage[];
  summarized_at?: string | null;
};

/** @deprecated Use chatStream() — /api/chat now returns SSE. */
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

export async function* chatStream(
  text: string,
  conversationId?: string | null,
  activeDocPath?: string | null,
): AsyncGenerator<ChatStreamEvent> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      text,
      conversation_id: conversationId ?? undefined,
      active_doc_path: activeDocPath ?? undefined,
    }),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.text()) || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || `请求失败 (${r.status})`);
  }
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      if (!part.trim()) continue;
      const lines = part.split("\n");
      const eventLine = lines.find((l) => l.startsWith("event: "));
      const dataLine = lines.find((l) => l.startsWith("data: "));
      if (eventLine && dataLine) {
        yield {
          event: eventLine.slice(7).trim(),
          data: JSON.parse(dataLine.slice(6)) as Record<string, unknown>,
        };
      }
    }
  }
}

function findActiveParallelIndex(timeline: TimelineBlock[]): number {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const block = timeline[i];
    if (block.type === "parallel" && block.duration_ms === undefined) {
      return i;
    }
  }
  return -1;
}

function updateToolBlock(
  blocks: TimelineBlock[],
  id: string,
  updater: (block: Extract<TimelineBlock, { type: "tool" }>) => TimelineBlock,
): TimelineBlock[] {
  return blocks.map((block) => {
    if (block.type === "tool" && block.id === id) {
      return updater(block);
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: updateToolBlock(block.children, id, updater),
      };
    }
    return block;
  });
}

export function updateTimeline(
  timeline: TimelineBlock[],
  event: string,
  data: Record<string, unknown>,
): TimelineBlock[] {
  if (event === "tool_start") {
    const query = toolQueryFromInput(data.input);
    const toolBlock: TimelineBlock = {
      type: "tool",
      id: data.id as string,
      tool: data.tool as string,
      label: (data.label as string) || TOOL_LABELS[data.tool as string] || (data.tool as string),
      ts: data.ts as string,
      status: "running",
      ...(query ? { query } : {}),
    };
    const parallelIdx = findActiveParallelIndex(timeline);
    if (parallelIdx >= 0) {
      return timeline.map((block, i) =>
        i === parallelIdx && block.type === "parallel"
          ? { ...block, children: [...block.children, toolBlock] }
          : block,
      );
    }
    return [...timeline, toolBlock];
  }

  if (event === "tool_result") {
    const id = data.id as string;
    return updateToolBlock(timeline, id, (block) => ({
      ...block,
      status: "done",
      summary: (data.summary as string) || "",
      sources: (data.sources as SourceRef[]) || [],
      ...(data.content ? { content: data.content as string } : {}),
      ...(data.duration_ms !== undefined
        ? { duration_ms: data.duration_ms as number }
        : {}),
      ...(typeof data.query === "string" && data.query.trim()
        ? { query: (data.query as string).trim() }
        : {}),
      ...(data.question_id
        ? { question_id: data.question_id as string }
        : {}),
      ...(data.question ? { question: data.question as string } : {}),
      ...(data.options
        ? { options: data.options as QuestionOption[] }
        : {}),
      ...(data.multi_select !== undefined
        ? { multi_select: data.multi_select as boolean }
        : {}),
    }));
  }

  if (event === "parallel_batch_start") {
    const parallelBlock: TimelineBlock = {
      type: "parallel",
      batch_id: data.batch_id as string,
      ts: data.ts as string,
      children: [],
    };
    return [...timeline, parallelBlock];
  }

  if (event === "parallel_batch_end") {
    const batchId = data.batch_id as string;
    return timeline.map((block) =>
      block.type === "parallel" && block.batch_id === batchId
        ? {
            ...block,
            ...(data.duration_ms !== undefined
              ? { duration_ms: data.duration_ms as number }
              : {}),
          }
        : block,
    );
  }

  if (event === "text_delta") {
    const delta = (data.delta as string) || "";
    const last = timeline[timeline.length - 1];
    if (last?.type === "text") {
      return [
        ...timeline.slice(0, -1),
        { ...last, content: last.content + delta },
      ];
    }
    return [
      ...timeline,
      { type: "text", ts: data.ts as string, content: delta },
    ];
  }

  return timeline;
}

export async function ingest(text: string) {
  return apiFetch<IngestResult>("/api/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

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

export async function uploadFile(file: File, category: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("category", category);
  return apiFetch<{ attachment: string; indexed: boolean }>("/api/upload", {
    method: "POST",
    body: fd,
  });
}

export async function getTree() {
  return apiFetch<{ docs: string[] }>("/api/tree");
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

export function downloadUrl(path: string) {
  return `${BASE}/api/download?path=${encodeURIComponent(path)}`;
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
export async function summarizeConversation(id: string) {
  return apiFetch<IngestResult>(
    `/api/conversations/${encodeURIComponent(id)}/summarize`,
    { method: "POST" },
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
    `${BASE}/api/docs/merge/active?path=${encodeURIComponent(path)}`,
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
    throw new Error(detail || `请求失败 (${r.status})`);
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
