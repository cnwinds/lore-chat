/**
 * 出站发送队列策略（flush / inject / pause）——与 UI 展示态分离的 deep module。
 */

import type { SendQueueItem } from "../../utils/sendQueue";

export type StreamEndInfo = {
  failed: boolean;
  aborted: boolean;
  detached?: boolean;
  awaitingUser?: boolean;
};

export type OutboundQueueSnapshot = {
  items: SendQueueItem[];
  paused: boolean;
  pendingGroup: SendQueueItem[] | null;
  flushing: boolean;
};

/** 观测断开：不暂停队列。失败/停止：还原 pending 并 pause。征询：pause。否则可 flush。 */
export function applyStreamEnd(
  snap: OutboundQueueSnapshot,
  info: StreamEndInfo,
): {
  items: SendQueueItem[];
  paused: boolean;
  pendingGroup: SendQueueItem[] | null;
  flushing: boolean;
  shouldFlush: boolean;
} {
  if (info.detached) {
    return {
      items: snap.items,
      paused: snap.paused,
      pendingGroup: snap.pendingGroup,
      flushing: false,
      shouldFlush: false,
    };
  }
  if (info.failed || info.aborted) {
    const pending = snap.pendingGroup;
    let next = snap.items.map((x) =>
      x.locked
        ? { ...x, locked: false, timing: "defer" as const, error: null }
        : x,
    );
    if (pending?.length) {
      next = [
        ...pending.map((g, i) => ({
          ...g,
          locked: false,
          error: info.failed && i === 0 ? "发送失败" : null,
        })),
        ...next,
      ];
    }
    return {
      items: next,
      paused: true,
      pendingGroup: null,
      flushing: false,
      shouldFlush: false,
    };
  }
  if (info.awaitingUser) {
    return {
      items: snap.items,
      paused: true,
      pendingGroup: null,
      flushing: false,
      shouldFlush: false,
    };
  }
  return {
    items: snap.items,
    paused: snap.paused,
    pendingGroup: null,
    flushing: false,
    shouldFlush: true,
  };
}

export function applyInjectDeferred(
  items: SendQueueItem[],
  injectId: string,
): SendQueueItem[] {
  return items.map((x) =>
    x.id === injectId || x.locked
      ? {
          ...x,
          locked: false,
          timing: "defer" as const,
          error: null,
        }
      : x,
  );
}

export function applyUserInjected(
  items: SendQueueItem[],
  injectId: string,
): SendQueueItem[] {
  return items.filter((x) => x.id !== injectId && !x.locked);
}
