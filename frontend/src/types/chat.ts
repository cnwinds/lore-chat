/** 聊天 / 会话领域类型（与 HTTP 传输层分离）。 */

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
  /** /api/ask 同步响应形状；产品 UI 使用 chatStream，不经此类型 */
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
  | {
      type: "conversation";
      cid: string;
      excerpt?: string;
      /** 消息级命中（ConversationFTS 桥接）才有；旧的整段会话兜底命中没有 */
      message_id?: string;
      start_char?: number;
      end_char?: number;
      offset_version?: string;
      ts?: string;
      role?: string;
      conversation_title?: string;
    };

export type TimelineBlock =
  | {
      type: "tool";
      id: string;
      tool: string;
      label: string;
      ts: string;
      status: "running" | "done" | "interrupted";
      /** 检索词 / 沙箱命令 / 生图提示词等 */
      query?: string;
      summary?: string;
      /** 沙箱等长任务的关键节点日志 */
      progress_log?: string[];
      sources?: SourceRef[];
      content?: string;
      duration_ms?: number;
      /** 前端本地：tool_start 时 Date.now()，供运行中秒表 */
      started_at_ms?: number;
      question_id?: string;
      question?: string;
      options?: QuestionOption[];
      multi_select?: boolean;
      choice_resolved?: string;
      /** edit_doc 修改点上下文预览 */
      preview?: string;
      reindex_mode?: string;
      applied?: number;
      /** generate_image 等产出的本地相对路径 */
      attachments?: string[];
      /** demo 写工具：preview_only */
      result_status?: string;
      demo_preview?: {
        kind: "doc" | "doc_edit" | "doc_meta" | "memory";
        path?: string;
        content?: string;
        action?: string;
      };
    }
  | {
      type: "parallel";
      batch_id: string;
      ts: string;
      children: TimelineBlock[];
      duration_ms?: number;
    }
  | { type: "text"; ts: string; content: string }
  | { type: "think"; ts: string; content: string }
  | {
      type: "user_inject";
      inject_id: string;
      ts: string;
      text: string;
      message_id?: string;
      client_message_id?: string;
      doc_context?: DocContextItem[];
      primary_doc?: string;
      attachments?: string[];
    };

export type DocContextItem = {
  path: string;
  kind: "document";
};

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  ts?: string;
  text?: string;
  timeline?: TimelineBlock[];
  sources?: SourceRef[];
  attachments?: string[];
  doc_context?: DocContextItem[] | string[];
  primary_doc?: string;
  intent?: "recall" | "remember";
  /** complete | interrupted — 服务端 turn/消息落库；error — 失败（可落库或仅前端流式失败） */
  status?: "complete" | "interrupted" | "error" | string;
  /** 本轮回复总耗时（毫秒），来自 SSE done 事件 */
  total_duration_ms?: number;
  /** 本轮实际使用的模型名 */
  model_name?: string;
  /** 是否因冷却/禁用/本轮失败排除而切换到更低优先级 */
  model_failover?: boolean;
  /** 该用户提问发送时是否开启联网（重新回复时回放） */
  web_enabled?: boolean;
  /** Mid-turn inject (client_message_id starts with inject:) */
  injected?: boolean;
  client_message_id?: string;
};

export type CumulativeInfo = {
  toolCumulative: Map<string, number>;
  parallelCumulative: Map<string, number>;
};

export type ChatStreamEvent = { event: string; data: Record<string, unknown> };

// 会改动知识库、需要刷新侧栏的工具
export const KB_MUTATING_TOOLS = [
  "write_doc",
  "write_kb_file",
  "delete_kb",
  "summarize_conversation",
  "edit_doc",
  "update_doc_meta",
  "move_entry",
  "move_doc",
  "publish_from_sandbox",
  "generate_image",
] as const;

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  summarized?: boolean;
  summary_path?: string | null;
};

export type Conversation = ConversationSummary & {
  messages: ChatMessage[];
  summarized_at?: string | null;
  active_turn_id?: string | null;
  active_turn?: {
    turn_id: string;
    status: string;
    started_at?: string;
  } | null;
};
