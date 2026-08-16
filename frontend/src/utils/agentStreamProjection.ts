/** Agent SSE 观测投影：纯 reduce + 结束策略（与 React hook 分离）。 */

import { KB_MUTATING_TOOLS, type ChatMessage, type SourceRef } from "../types/chat";
import { kbPathFromToolResult, timelineAwaitsUserAnswer } from "./chatMessage";
import { nowIsoDisplay } from "./displayTime";
import { applyTimelineEvent, mergeServerTimeline } from "./timelineStream";

export type StreamReduceState = {
  streamFailed: boolean;
  awaitingUser: boolean;
  serverTimeline: boolean;
  assistant: ChatMessage;
  /** 本事件触发 KB 变更回调；`null` 表示无具体路径仍需刷新 */
  kbNotify?: string | null;
  userInjectId?: string;
  injectDeferredId?: string;
};

export type StreamReduceResult = {
  state: StreamReduceState;
  /** true → 停止消费后续事件 */
  stop: boolean;
};

export function reduceStreamEvent(
  state: StreamReduceState,
  event: string,
  data: Record<string, unknown>,
): StreamReduceResult {
  if (event === "error") {
    const message = (data.message as string) || "请求失败";
    return {
      state: {
        ...state,
        streamFailed: true,
        assistant: {
          ...state.assistant,
          text: `错误：${message}`,
          status: "error",
        },
      },
      stop: true,
    };
  }

  if (event === "timeline_state") {
    const incoming = (data.timeline as ChatMessage["timeline"]) || [];
    const assistantText =
      typeof data.assistant_text === "string" ? data.assistant_text : undefined;
    return {
      state: {
        ...state,
        serverTimeline: true,
        assistant: mergeServerTimeline(state.assistant, incoming, assistantText),
      },
      stop: false,
    };
  }

  if (event === "user_inject") {
    const injectId = data.inject_id as string;
    let assistant = state.assistant;
    if (!state.serverTimeline) {
      assistant = {
        ...assistant,
        timeline: applyTimelineEvent(assistant.timeline ?? [], event, data),
      };
    }
    return {
      state: { ...state, assistant, userInjectId: injectId },
      stop: false,
    };
  }

  if (event === "inject_deferred") {
    return {
      state: {
        ...state,
        injectDeferredId: data.inject_id as string,
      },
      stop: false,
    };
  }

  if (event === "model_selected") {
    const model = typeof data.model === "string" ? data.model : undefined;
    return {
      state: {
        ...state,
        assistant: {
          ...state.assistant,
          model_name: model,
          model_failover: Boolean(data.failover),
        },
      },
      stop: false,
    };
  }

  const assistant = { ...state.assistant };
  let awaitingUser = state.awaitingUser;
  let kbNotify: string | null | undefined;

  // 与 backend turn_hub._STRUCTURAL_TIMELINE_EVENTS 互补（ADR 2026-08-08 §5）。
  const STREAM_LOCAL_DELTA_EVENTS = new Set([
    "text_delta",
    "think_delta",
    "tool_progress",
  ]);
  // 结构事件由 timeline_state 投影；token/进度增量即使已切 serverTimeline 也本地 reduce，
  // 避免后端对每个 delta 再推全量快照（O(n²) 内存）。
  if (event !== "done" && (!state.serverTimeline || STREAM_LOCAL_DELTA_EVENTS.has(event))) {
    assistant.timeline = applyTimelineEvent(assistant.timeline ?? [], event, data);
  }
  // 持久回合不再随 token 推 assistant_text；仅在已切投影后累加，避免 ephemeral 双源。
  if (state.serverTimeline && event === "text_delta") {
    const delta = typeof data.delta === "string" ? data.delta : "";
    if (delta) {
      assistant.text = (assistant.text || "") + delta;
    }
  }
  if (event === "done") {
    assistant.sources = (data.sources as SourceRef[]) || [];
    if (data.total_duration_ms !== undefined) {
      assistant.total_duration_ms = data.total_duration_ms as number;
    }
    assistant.ts = nowIsoDisplay();
    awaitingUser = timelineAwaitsUserAnswer(assistant.timeline);
  }

  if (event === "tool_result") {
    if ((KB_MUTATING_TOOLS as readonly string[]).includes(data.tool as string)) {
      kbNotify = kbPathFromToolResult(data) ?? null;
    }
    if (Array.isArray(data.attachments) && data.attachments.length) {
      const prev = assistant.attachments ?? [];
      const seen = new Set(prev);
      const merged = [...prev];
      for (const p of data.attachments) {
        if (typeof p === "string" && p && !seen.has(p)) {
          seen.add(p);
          merged.push(p);
        }
      }
      assistant.attachments = merged;
    }
    if (
      (data.tool === "ask_user" || data.tool === "sandbox_run") &&
      data.question_id &&
      Array.isArray(data.options) &&
      (data.options as unknown[]).length > 0
    ) {
      awaitingUser = true;
    }
  }

  return {
    state: {
      ...state,
      assistant,
      awaitingUser,
      kbNotify,
    },
    stop: false,
  };
}

export type ObservationEndInfo = {
  streamFailed: boolean;
  aborted: boolean;
  detached: boolean;
  awaitingUser: boolean;
};

/** 是否在观测结束后从服务端重载消息列表。 */
export function shouldReloadConversation(info: ObservationEndInfo): "full" | "aborted" | "none" {
  // 流失败保留本地错误气泡（可能尚未落库）；刷新后靠服务端 interrupted/error 正文
  if (info.streamFailed || info.detached) return "none";
  if (info.aborted) return "aborted";
  return "full";
}
