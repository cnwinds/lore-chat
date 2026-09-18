/**
 * 出站发送队列编排（薄客户端层）。
 *
 * 注入与续发的驱动已迁移到服务端（TurnHub on_turn_end → 队列 drain），
 * 客户端只负责：镜像同步、停止/继续/重试/跳过/清空的转发，
 * 以及流结束/注入被拒后的镜像刷新。
 */

import { useCallback, useRef } from "react";
import type { useSendQueue } from "./useSendQueue";
import type { SendQueueItem } from "../../utils/sendQueue";

type SendQueueApi = ReturnType<typeof useSendQueue>;

type Options = {
  sendQueue: SendQueueApi;
  streaming: boolean;
  streamingRef: MutableRefObject<boolean>;
  conversationIdRef: MutableRefObject<string | null>;
  runOutbound: (group: SendQueueItem[]) => Promise<boolean>;
};

type MutableRefObject<T> = { current: T };

export function useOutboundOrchestrator({
  sendQueue,
  runOutbound: _runOutbound,
}: Options) {
  const itemsRef = useRef(sendQueue.items);
  const pausedRef = useRef(sendQueue.paused);
  itemsRef.current = sendQueue.items;
  pausedRef.current = sendQueue.paused;

  const refresh = useCallback(() => {
    void sendQueue.refresh();
  }, [sendQueue]);

  // 流结束（完成/失败/征询/停止）：服务端 drain 已做出暂停或续发决策，
  // 客户端延迟刷新镜像即可；注入被服务端拒绝(409)时服务端已改为排队。
  const handleStreamEnd = useCallback(
    (_info: unknown) => {
      window.setTimeout(refresh, 1200);
    },
    [refresh],
  );

  const handleInjectDeferred = useCallback(
    (_id: string) => {
      refresh();
    },
    [refresh],
  );

  const handleUserInjected = useCallback(
    (_id: string) => {
      refresh();
    },
    [refresh],
  );

  const handleStop = useCallback(() => {
    // 服务端 stop 通道同样会暂停队列；本地仅标记
    sendQueue.setPaused(true);
  }, [sendQueue]);

  const handleContinue = useCallback(() => {
    sendQueue.setPaused(false);
    refresh();
  }, [sendQueue, refresh]);

  const handleRetry = useCallback(() => {
    sendQueue.setItems(
      itemsRef.current.map((x) => ({ ...x, error: null, locked: false })),
    );
    sendQueue.setPaused(false);
    refresh();
  }, [sendQueue, refresh]);

  const handleSkipFailed = useCallback(() => {
    const failed = itemsRef.current.filter((x) => x.error);
    for (const f of failed) {
      if (!f.locked) sendQueue.removeItem(f.id);
    }
    sendQueue.setPaused(false);
    refresh();
  }, [sendQueue]);

  const flushQueue = useCallback(() => {
    // 兼容旧调用点：真正的续发由服务端 drain 完成
    refresh();
  }, [refresh]);

  const maybeInjectFront = useCallback(() => {
    refresh();
  }, [refresh]);

  const enqueueAndKick = useCallback(
    (item: SendQueueItem) => {
      void sendQueue.enqueue({
        text: item.text,
        timing: item.timing,
        doc_context: item.doc_context,
        primary_doc: item.primary_doc,
        attachments: item.attachments,
        webEnabled: item.webEnabled,
        mentions: item.mentions,
      });
      refresh();
    },
    [sendQueue, refresh],
  );

  const unpauseAndFlush = useCallback(() => {
    sendQueue.setPaused(false);
    refresh();
  }, [sendQueue, refresh]);

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
