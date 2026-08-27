/** 观测断开后以服务端 active_turn / messages 为准的 reconcile 策略。 */

import type { Conversation } from "../../api";

export const RECONCILE_DELAYS_MS = [0, 400, 1200];

export type ObservationEndInfo = {
  completed: boolean;
  aborted: boolean;
  /** 服务端 SSE error 事件 */
  serverStreamError: boolean;
  /** 未收到 done 且非用户停止：断线、detach、流静默结束等 */
  observationLost: boolean;
  awaitingUser: boolean;
};

export type ReconcileOutcome = "resumed" | "settled" | "failed";

export function buildObservationEnd(params: {
  completed: boolean;
  serverStreamError: boolean;
  aborted: boolean;
  awaitingUser: boolean;
}): ObservationEndInfo {
  const { completed, serverStreamError, aborted, awaitingUser } = params;
  return {
    completed,
    aborted,
    serverStreamError,
    awaitingUser,
    observationLost: !completed && !aborted,
  };
}

export function needsServerReconcile(info: ObservationEndInfo): boolean {
  return info.observationLost;
}

export function shouldReloadConversation(
  info: ObservationEndInfo,
): "full" | "aborted" | "none" | "reconcile" {
  if (needsServerReconcile(info)) return "reconcile";
  if (info.aborted) return "aborted";
  if (info.completed) return "full";
  return "none";
}

/** 映射到出站队列 / 旧 StreamEnd 契约。reconcile 进行中或 detach 不切队列。 */
export function toStreamEndPayload(
  info: ObservationEndInfo,
  opts?: { reconcileFailed?: boolean },
): {
  failed: boolean;
  aborted: boolean;
  detached: boolean;
  awaitingUser: boolean;
} {
  if (needsServerReconcile(info) && !opts?.reconcileFailed) {
    return {
      failed: false,
      aborted: false,
      detached: true,
      awaitingUser: false,
    };
  }
  return {
    failed: info.serverStreamError || !!opts?.reconcileFailed,
    aborted: info.aborted,
    detached: false,
    awaitingUser:
      info.completed && info.awaitingUser && !info.serverStreamError,
  };
}

export async function fetchConversationWithRetry(
  cid: string,
  fetchConv: (id: string) => Promise<Conversation>,
  delays: number[] = RECONCILE_DELAYS_MS,
): Promise<Conversation | null> {
  for (let i = 0; i < delays.length; i++) {
    const delay = delays[i];
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    try {
      return await fetchConv(cid);
    } catch {
      /* retry */
    }
  }
  return null;
}

export function isActiveTurnRunning(conv: Conversation): boolean {
  return conv.active_turn?.status === "running";
}
