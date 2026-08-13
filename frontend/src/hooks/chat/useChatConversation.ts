import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { getConversation, type ChatMessage } from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
} from "../../utils/chatMessage";
import {
  scrollToMessageHighlight,
  type JumpTarget,
} from "./useConversationJump";

type Options = {
  conversationId: string | null;
  skipLoadRef: MutableRefObject<string | null>;
  streamingRef: MutableRefObject<boolean>;
  pendingJump?: JumpTarget | null;
  onJumpHandled?: () => void;
  /** Called when loaded conversation has a server-side running turn. */
  onActiveTurn?: (conversationId: string, startedAt?: string | null) => void;
};

/**
 * 跳转会话后：无 messageId 时只要会话已切过去即可完成（不必等消息加载）。
 * 有 messageId 时等历史加载完再滚到目标消息。
 */
export function useChatConversation({
  conversationId,
  skipLoadRef,
  streamingRef,
  pendingJump = null,
  onJumpHandled,
  onActiveTurn,
}: Options) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  const pendingJumpRef = useRef<JumpTarget | null>(null);
  const onActiveTurnRef = useRef(onActiveTurn);
  const onJumpHandledRef = useRef(onJumpHandled);
  onActiveTurnRef.current = onActiveTurn;
  onJumpHandledRef.current = onJumpHandled;

  useEffect(() => {
    if (pendingJump) {
      pendingJumpRef.current = pendingJump;
    }
  }, [pendingJump]);

  // 仅切换会话（无 messageId）：activeConversationId 对齐即可完成跳转
  useEffect(() => {
    const target = pendingJumpRef.current;
    if (!target || target.messageId) return;
    if (target.conversationId !== conversationId) return;
    pendingJumpRef.current = null;
    onJumpHandledRef.current?.();
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) {
      setMsgs([]);
      setSummarized(false);
      setSummaryPath(null);
      return;
    }
    if (skipLoadRef.current === conversationId || streamingRef.current) {
      return;
    }
    let cancelled = false;
    setLoadingHistory(true);
    getConversation(conversationId)
      .then((conv) => {
        if (!cancelled && !streamingRef.current) {
          setMsgs(
            conv.messages.map((m) =>
              normalizeLoadedMessage({
                ...m,
                injected: isInjectedUserMessage(m),
              }),
            ),
          );
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
          if (conv.active_turn?.status === "running") {
            onActiveTurnRef.current?.(
              conversationId,
              conv.active_turn.started_at,
            );
          }
        }
      })
      .catch(() => {
        if (!cancelled && !streamingRef.current) {
          setMsgs([]);
          setSummarized(false);
          setSummaryPath(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    const target = pendingJumpRef.current;
    if (!target?.messageId || target.conversationId !== conversationId) return;
    if (loadingHistory || msgs.length === 0) return;

    const range =
      target.startChar !== undefined && target.endChar !== undefined
        ? { start: target.startChar, end: target.endChar }
        : undefined;

    const frame = requestAnimationFrame(() => {
      const ok = scrollToMessageHighlight(
        target.messageId!,
        range,
        target.offsetVersion,
      );
      if (ok) {
        pendingJumpRef.current = null;
        onJumpHandledRef.current?.();
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [conversationId, loadingHistory, msgs]);

  return {
    msgs,
    setMsgs,
    loadingHistory,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
  };
}

export type { JumpTarget };
