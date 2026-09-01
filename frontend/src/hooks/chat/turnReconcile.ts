/** 观测断开后以服务端 active_turn / messages 为准的 reconcile 策略。 */

import type { ActiveTurnStatus, Conversation } from "../../api";

/** 含移动端网卡唤醒余量：约十几秒内多次探测。 */
export const RECONCILE_DELAYS_MS = [0, 500, 1500, 3500, 8000];

export type ObservationEndInfo = {
  completed: boolean;
  aborted: boolean;
  /** 服务端 SSE error 事件 */
  serverStreamError: boolean;
  /** 未收到 done 且非用户停止：断线、detach、流静默结束等 */
  observationLost: boolean;
  awaitingUser: boolean;
};

export type ReconcileOutcome =
  | "resumed"
  | "settled"
  | "failed"
  | "network_unreachable";

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

/** 映射到出站队列 / 旧 StreamEnd 契约。reconcile 进行中、detach、网络不可达不切队列。 */
export function toStreamEndPayload(
  info: ObservationEndInfo,
  opts?: { reconcileFailed?: boolean; networkUnreachable?: boolean },
): {
  failed: boolean;
  aborted: boolean;
  detached: boolean;
  awaitingUser: boolean;
} {
  if (opts?.networkUnreachable) {
    return {
      failed: false,
      aborted: false,
      detached: true,
      awaitingUser: false,
    };
  }
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

export async function fetchWithRetry<T>(
  cid: string,
  fetchFn: (id: string) => Promise<T>,
  delays: number[] = RECONCILE_DELAYS_MS,
): Promise<T | null> {
  for (let i = 0; i < delays.length; i++) {
    const delay = delays[i];
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    try {
      return await fetchFn(cid);
    } catch {
      /* retry */
    }
  }
  return null;
}

/** @deprecated Prefer fetchActiveTurnStatusWithRetry for reconcile probes. */
export async function fetchConversationWithRetry(
  cid: string,
  fetchConv: (id: string) => Promise<Conversation>,
  delays: number[] = RECONCILE_DELAYS_MS,
): Promise<Conversation | null> {
  return fetchWithRetry(cid, fetchConv, delays);
}

export async function fetchActiveTurnStatusWithRetry(
  cid: string,
  fetchStatus: (id: string) => Promise<ActiveTurnStatus>,
  delays: number[] = RECONCILE_DELAYS_MS,
): Promise<ActiveTurnStatus | null> {
  return fetchWithRetry(cid, fetchStatus, delays);
}

export function isActiveTurnRunning(status: ActiveTurnStatus): boolean {
  return status.status === "running" && status.observable;
}

export function isActiveTurnOrphaned(status: ActiveTurnStatus): boolean {
  return status.status === "orphaned";
}

/** 兼容 getConversation.active_turn 语义（加载历史、normalize）。 */
export function isActiveTurnRunningConv(conv: Conversation): boolean {
  return conv.active_turn?.status === "running";
}
