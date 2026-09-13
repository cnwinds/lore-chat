import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConversation,
  getConversationMessages,
  type ChatMessage,
} from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
} from "../../utils/chatMessage";
import {
  shouldProtectStreamingHistory,
  type StreamOwnership,
} from "./streamOwnership";
import {
  scrollToMessageHighlight,
  type JumpTarget,
} from "./useConversationJump";

type Options = {
  conversationId: string | null;
  /** 当前角色；会话不属于该角色时不当成 tip 展示 */
  roleId?: string | null;
  skipLoadRef: { current: string | null };
  streamOwnership: StreamOwnership;
  pendingJump?: JumpTarget | null;
  onJumpHandled?: () => void;
  /** Called when loaded conversation has a server-side running turn. */
  onActiveTurn?: (
    conversationId: string,
    startedAt?: string | null,
    respondingRoleId?: string | null,
  ) => void;
  /** 首屏只取尾部 N 条；搜索定位走附近窗口，不在这里拉全量 */
  messageTail?: number;
  /** 已加载会话不属于当前角色 */
  onRoleMismatch?: (conversationId: string, roleId: string) => void;
};

function toLoadedMessages(
  messages: ChatMessage[],
  activeTurnRunning: boolean,
): ChatMessage[] {
  return messages.map((m) =>
    normalizeLoadedMessage(
      {
        ...m,
        injected: isInjectedUserMessage(m),
      },
      { activeTurnRunning },
    ),
  );
}

/**
 * 跳转会话后：无 messageId 时只要会话已切过去即可完成（不必等消息加载）。
 * 有 messageId 时等历史加载完再滚到目标消息。
 */
export function useChatConversation({
  conversationId,
  roleId = null,
  skipLoadRef,
  streamOwnership,
  pendingJump = null,
  onJumpHandled,
  onActiveTurn,
  messageTail,
  onRoleMismatch,
}: Options) {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [olderMessageCount, setOlderMessageCount] = useState(0);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  const [respondingRoleId, setRespondingRoleId] = useState<string | null>(null);
  const pendingJumpRef = useRef<JumpTarget | null>(null);
  const onActiveTurnRef = useRef(onActiveTurn);
  const onJumpHandledRef = useRef(onJumpHandled);
  const messageTailRef = useRef(messageTail);
  const roleIdRef = useRef(roleId);
  const onRoleMismatchRef = useRef(onRoleMismatch);
  onActiveTurnRef.current = onActiveTurn;
  onJumpHandledRef.current = onJumpHandled;
  messageTailRef.current = messageTail;
  roleIdRef.current = roleId;
  onRoleMismatchRef.current = onRoleMismatch;

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
      streamOwnership.msgsConversationIdRef.current = null;
      setSummarized(false);
      setSummaryPath(null);
      setOlderMessageCount(0);
      setRespondingRoleId(null);
      return;
    }
    // Only skip reload for the conversation we just created / own optimistically.
    // Do NOT skip because some *other* conversation is still streaming — that left
    // the previous chat's messages on screen after switching.
    if (skipLoadRef.current === conversationId) {
      setOlderMessageCount(0);
      return;
    }
    let cancelled = false;
    const loadedFor = conversationId;
    // Drop foreign messages immediately so a fast send/resume cannot append onto
    // another conversation's bubbles while history is in flight.
    if (streamOwnership.msgsConversationIdRef.current !== loadedFor) {
      setMsgs([]);
      streamOwnership.msgsConversationIdRef.current = null;
    }
    setLoadingHistory(true);

    const applyIfSafe = (apply: () => void) => {
      if (cancelled) return;
      // Protect in-flight optimistic UI only when msgs already belong to this stream.
      // After A→B→A, msgs may still be B's while the stream owns A — must reload.
      if (shouldProtectStreamingHistory(streamOwnership, loadedFor)) {
        return;
      }
      apply();
    };

    const tail = messageTail ? messageTail : undefined;

    const req = tail
      ? getConversation(conversationId, { tail })
      : getConversation(conversationId);

    req
      .then((conv) => {
        applyIfSafe(() => {
          const expectedRole = roleIdRef.current;
          const loadedRole = (conv.role_id || "default").trim() || "default";
          const kind = (conv as { kind?: string }).kind || "owner_dm";
          if (
            expectedRole &&
            loadedRole !== expectedRole &&
            kind !== "peer_dm" &&
            kind !== "group"
          ) {
            setMsgs([]);
            setSummarized(false);
            setSummaryPath(null);
            setOlderMessageCount(0);
            onRoleMismatchRef.current?.(loadedFor, expectedRole);
            return;
          }
          const activeTurnRunning = conv.active_turn?.status === "running";
          setMsgs(toLoadedMessages(conv.messages, activeTurnRunning));
          streamOwnership.msgsConversationIdRef.current = loadedFor;
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
          setOlderMessageCount(conv.older_message_count ?? 0);
          setRespondingRoleId(conv.active_turn?.responding_role_id ?? null);
          if (conv.active_turn?.status === "running") {
            onActiveTurnRef.current?.(
              loadedFor,
              conv.active_turn.started_at,
              conv.active_turn.responding_role_id,
            );
          }
        });
      })
      .catch(() => {
        applyIfSafe(() => {
          setMsgs([]);
          streamOwnership.msgsConversationIdRef.current = loadedFor;
          setSummarized(false);
          setSummaryPath(null);
          setOlderMessageCount(0);
        });
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId, roleId, skipLoadRef, streamOwnership, messageTail]);

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

  const loadOlderMessages = useCallback(async () => {
    if (
      !conversationId ||
      loadingOlderMessages ||
      loadingHistory ||
      olderMessageCount <= 0
    ) {
      return false;
    }
    const firstId = msgs.find((m) => m.id)?.id;
    if (!firstId) return false;
    setLoadingOlderMessages(true);
    try {
      const page = await getConversationMessages(conversationId, {
        beforeId: firstId,
        limit: messageTailRef.current || 16,
      });
      setMsgs((prev) => {
        const seen = new Set(
          prev.map((m) => m.id).filter((id): id is string => !!id),
        );
        const prepend = toLoadedMessages(page.messages, false).filter(
          (m) => !m.id || !seen.has(m.id),
        );
        return [...prepend, ...prev];
      });
      setOlderMessageCount(page.older_message_count);
      return page.messages.length > 0;
    } catch {
      return false;
    } finally {
      setLoadingOlderMessages(false);
    }
  }, [
    conversationId,
    loadingOlderMessages,
    loadingHistory,
    olderMessageCount,
    msgs,
  ]);

  return {
    msgs,
    setMsgs,
    loadingHistory,
    loadingOlderMessages,
    olderMessageCount,
    loadOlderMessages,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
    respondingRoleId,
  };
}

export type { JumpTarget };
