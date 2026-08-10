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
        assistant: { ...state.assistant, text: `错误：${message}` },
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

  if (event !== "done" && !state.serverTimeline) {
    assistant.timeline = applyTimelineEvent(assistant.timeline ?? [], event, data);
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
  if (info.streamFailed || info.detached) return "none";
  if (info.aborted) return "aborted";
  return "full";
}
