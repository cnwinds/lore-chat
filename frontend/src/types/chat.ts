/** 聊天 / 会话领域类型（与 HTTP 传输层分离）。 */

export type QuestionOption = { id: string; label: string };
export type Question = {
  id: string;
  question: string;
  options: QuestionOption[];
  multi_select?: boolean;
  payload?: {
    kind?: string;
    role_id?: string;
    role_name?: string;
    [key: string]: unknown;
  };
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
      /** 秒表锚点：优先服务端 tool ts；本地 tool_start 在 ts 不可解析时回退 Date.now() */
      started_at_ms?: number;
      question_id?: string;
      question?: string;
      options?: QuestionOption[];
      multi_select?: boolean;
      choice_resolved?: string;
      role_id?: string;
      role_name?: string;
      room_id?: string;
      message_id?: string;
      target_role_id?: string;
      target_role_name?: string;
      targets?: { id: string; name: string }[];
      wake_status?: string;
      expect_reply?: boolean;
      hop?: number;
      error?: string;
      turn_id?: string;
      /** edit_doc 修改点上下文预览 */
      preview?: string;
      reindex_mode?: string;
      applied?: number;
      /** generate_image 等产出的本地相对路径 */
      attachments?: string[];
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
  speaker_kind?: "user" | "role" | "system" | string;
  speaker_id?: string;
  speaker_name?: string;
  hop?: number;
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

export type RoomParticipant = {
  id: string;
  name: string;
  avatar?: string | null;
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  role_id?: string;
  kind?: "owner_dm" | "peer_dm" | "group" | "group_card" | string;
  peer_role_id?: string | null;
  participant_role_ids?: string[];
  participants?: RoomParticipant[];
  avatar?: string | null;
  excerpt?: string;
  card_status?: string;
  room_id?: string;
  summarized?: boolean;
  summary_path?: string | null;
};

export type RoleSummary = {
  id: string;
  name: string;
  avatar: string | null;
  system_prompt: string;
  is_default: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
  /** 该角色最近一次会话活动；列表右侧时间用这个，不是人设更新时间 */
  last_active_at?: string | null;
  /** 该角色最近一条助手回复的单行预览 */
  last_reply_preview?: string | null;
};

export type ActiveTurnStatus = {
  conversation_id: string;
  turn_id: string | null;
  status: "running" | "orphaned" | "complete" | "interrupted" | null;
  started_at: string | null;
  last_seq: number | null;
  observable: boolean;
};

export type RoomSummary = {
  id: string;
  title: string;
  kind: "peer_dm" | "group" | string;
  created_at?: string;
  updated_at?: string;
  avatar?: string | null;
  participant_role_ids: string[];
  participant_names?: string[];
  participants?: RoomParticipant[];
  peer_role_id?: string | null;
};

export type RoomStatus = {
  id: string;
  kind: string;
  title?: string;
  state: "queued" | "working" | "awaiting_user" | "done" | "idle" | "failed" | string;
  preview?: string;
  queued_count: number;
  pending_questions: Question[];
  active_turn?: { turn_id: string; status: string; started_at?: string } | null;
  participant_role_ids: string[];
  participant_names?: string[];
  peer_role_id?: string | null;
  updated_at?: string;
  last_message_at?: string | null;
};

export type Conversation = ConversationSummary & {
  messages: ChatMessage[];
  summarized_at?: string | null;
  active_turn_id?: string | null;
  active_turn?: {
    turn_id: string;
    status: string;
    started_at?: string;
    responding_role_id?: string | null;
  } | null;
  /** 当前页之前还有多少条未加载消息（tail / 向前翻页） */
  older_message_count?: number;
  /** 当前页之后还有多少条（around 窗口；tail 恒为 0） */
  newer_message_count?: number;
};
