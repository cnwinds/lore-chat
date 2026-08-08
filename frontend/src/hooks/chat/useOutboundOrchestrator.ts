/**
 * 出站发送队列编排：flush / inject / stream-end / 暂停续发。
 * 策略纯函数在 outboundQueue；本 hook 持有 refs 与副作用。
 */

import { useCallback, useEffect, useRef, type MutableRefObject } from "react";
import { chatInject } from "../../api";
import {
  mergeGroupText,
  takeNextGroup,
  type SendQueueItem,
} from "../../utils/sendQueue";
import type { useSendQueue } from "./useSendQueue";
import {
  applyInjectDeferred,
  applyStreamEnd,
  applyUserInjected,
  type StreamEndInfo,
} from "./outboundQueue";

type SendQueueApi = ReturnType<typeof useSendQueue>;

type RunOutbound = (group: SendQueueItem[]) => Promise<boolean>;

type Options = {
  sendQueue: SendQueueApi;
  streaming: boolean;
  streamingRef: MutableRefObject<boolean>;
  conversationIdRef: MutableRefObject<string | null>;
  runOutbound: RunOutbound;
};

export function useOutboundOrchestrator({
  sendQueue,
  streaming,
  streamingRef,
  conversationIdRef,
  runOutbound,
}: Options) {
  const itemsRef = useRef(sendQueue.items);
  const pausedRef = useRef(sendQueue.paused);
  const flushingRef = useRef(false);
  const pendingGroupRef = useRef<SendQueueItem[] | null>(null);
  itemsRef.current = sendQueue.items;
  pausedRef.current = sendQueue.paused;

  const flushQueueRef = useRef<() => Promise<void>>(async () => {});
  const maybeInjectFrontRef = useRef<() => Promise<void>>(async () => {});

  const handleStreamEnd = useCallback(
    (info: StreamEndInfo) => {
      const next = applyStreamEnd(
        {
          items: itemsRef.current,
          paused: pausedRef.current,
          pendingGroup: pendingGroupRef.current,
          flushing: flushingRef.current,
        },
        info,
      );
      itemsRef.current = next.items;
      pendingGroupRef.current = next.pendingGroup;
      flushingRef.current = next.flushing;
      sendQueue.setPaused(next.paused);
      sendQueue.setItems(next.items);
      if (next.shouldFlush) {
        queueMicrotask(() => {
          void flushQueueRef.current();
        });
      }
    },
    [sendQueue],
  );

  const handleInjectDeferred = useCallback(
    (injectId: string) => {
      const next = applyInjectDeferred(itemsRef.current, injectId);
      itemsRef.current = next;
      sendQueue.setItems(next);
      console.info("本轮无法插入，已改为回合后再发", injectId);
    },
    [sendQueue],
  );

  const handleUserInjected = useCallback(
    (injectId: string) => {
      const next = applyUserInjected(itemsRef.current, injectId);
      itemsRef.current = next;
      sendQueue.setItems(next);
    },
    [sendQueue],
  );

  const flushQueue = useCallback(async () => {
    if (flushingRef.current || streamingRef.current || pausedRef.current) return;
    const taken = takeNextGroup(itemsRef.current);
    if (!taken) return;
    flushingRef.current = true;
    const { group, rest } = taken;
    pendingGroupRef.current = group;
    itemsRef.current = rest;
    sendQueue.setItems(rest);
    try {
      const started = await runOutbound(group);
      if (!started) {
        pendingGroupRef.current = null;
        const restored = [...group, ...itemsRef.current];
        itemsRef.current = restored;
        sendQueue.setItems(restored);
        flushingRef.current = false;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "发送失败";
      pendingGroupRef.current = null;
      sendQueue.setPaused(true);
      const restored = [
        ...group.map((g, i) => ({
          ...g,
          locked: false,
          error: i === 0 ? msg : null,
        })),
        ...itemsRef.current,
      ];
      itemsRef.current = restored;
      sendQueue.setItems(restored);
      flushingRef.current = false;
    }
  }, [runOutbound, sendQueue, streamingRef]);

  flushQueueRef.current = flushQueue;

  const maybeInjectFront = useCallback(async () => {
    if (!streamingRef.current || pausedRef.current) return;
    const items = itemsRef.current;
    const taken = takeNextGroup(items);
    if (!taken || taken.group[0].timing !== "inject") return;
    if (taken.group.some((g) => g.locked)) return;
    const cid = conversationIdRef.current;
    if (!cid) return;

    const { group, rest } = taken;
    const injectId = group[0].id;
    const locked = [...group.map((g) => ({ ...g, locked: true })), ...rest];
    itemsRef.current = locked;
    sendQueue.setItems(locked);
    try {
      await chatInject({
        conversationId: cid,
        text: mergeGroupText(group),
        injectId,
        clientMessageId: `inject:${injectId}`,
        docContext: group[0].doc_context,
        primaryDocPath: group[0].primary_doc,
        attachments: group[0].attachments,
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      const deferred = [
        ...group.map((g) => ({
          ...g,
          locked: false,
          timing: "defer" as const,
          error: null as string | null,
        })),
        ...rest,
      ];
      if (status === 409) {
        itemsRef.current = deferred;
        sendQueue.setItems(deferred);
        console.info("本轮无法插入，已改为回合后再发");
      } else {
        const msg = err instanceof Error ? err.message : "注入失败";
        const failed = [
          {
            ...group[0],
            locked: false,
            timing: "defer" as const,
            error: msg,
          },
          ...group.slice(1).map((g) => ({
            ...g,
            locked: false,
            timing: "defer" as const,
          })),
          ...rest,
        ];
        itemsRef.current = failed;
        sendQueue.setItems(failed);
        sendQueue.setPaused(true);
      }
    }
  }, [sendQueue, streamingRef, conversationIdRef]);

  maybeInjectFrontRef.current = maybeInjectFront;

  useEffect(() => {
    if (streaming) {
      void maybeInjectFrontRef.current();
    }
  }, [streaming, sendQueue.items]);

  const enqueueAndKick = useCallback(
    (item: SendQueueItem) => {
      const next = [...itemsRef.current, item];
      itemsRef.current = next;
      sendQueue.setItems(next);
      if (!streamingRef.current && !sendQueue.paused) {
        void flushQueue();
      } else if (streamingRef.current) {
        void maybeInjectFront();
      }
    },
    [flushQueue, maybeInjectFront, sendQueue, streamingRef],
  );

  const handleStop = useCallback(() => {
    sendQueue.setPaused(true);
  }, [sendQueue]);

  const handleContinue = useCallback(() => {
    sendQueue.setPaused(false);
    sendQueue.setItems(
      itemsRef.current.map((x) => ({ ...x, error: null, locked: false })),
    );
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }, [sendQueue]);

  const handleRetry = useCallback(() => {
    sendQueue.setItems(itemsRef.current.map((x) => ({ ...x, error: null })));
    sendQueue.setPaused(false);
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }, [sendQueue]);

  const handleSkipFailed = useCallback(() => {
    const items = itemsRef.current;
    const next = items[0]?.error
      ? items.slice(1)
      : items.filter((x) => !x.error);
    sendQueue.setItems(next);
    sendQueue.setPaused(false);
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }, [sendQueue]);

  const unpauseAndFlush = useCallback(() => {
    sendQueue.setPaused(false);
    pausedRef.current = false;
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }, [sendQueue]);

  return {
    itemsRef,
    pausedRef,
    flushQueue,
    maybeInjectFront,
    enqueueAndKick,
    handleStreamEnd,
    handleInjectDeferred,
    handleUserInjected,
    handleStop,
    handleContinue,
    handleRetry,
    handleSkipFailed,
    unpauseAndFlush,
  };
}
