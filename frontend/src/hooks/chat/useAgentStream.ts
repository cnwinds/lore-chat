import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
import {
  chatStream,
  createConversation,
  getConversation,
  observeActiveTurnStream,
  stopChat,
  titleFromText,
  type ChatMessage,
  type ChatStreamEvent,
  type DocContextItem,
} from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
} from "../../utils/chatMessage";
import { nowIsoDisplay } from "../../utils/displayTime";
import { newId } from "../../utils/id";
import {
  reduceStreamEvent,
  shouldReloadConversation,
} from "../../utils/agentStreamProjection";
import {
  isStreamingForView,
  type StreamOwnership,
} from "./streamOwnership";

export type DocContext = {
  trayPaths: string[];
  docContext: DocContextItem[];
  primary: string | null;
};

export type StreamEndInfo = {
  failed: boolean;
  /** Explicit stop — turn cancelled on server. */
  aborted: boolean;
  /** Observation SSE closed; turn may still be running server-side. */
  detached?: boolean;
  conversationId: string | null;
  awaitingUser?: boolean;
};

type UseAgentStreamOptions = {
  conversationId: string | null;
  previewPath?: string | null;
  webEnabled: boolean;
  docContextItems: DocContextItem[];
  primaryDocPath: string | null;
  msgs: ChatMessage[];
  setMsgs: Dispatch<SetStateAction<ChatMessage[]>>;
  setSummarized: Dispatch<SetStateAction<boolean>>;
  setSummaryPath: Dispatch<SetStateAction<string | null>>;
  conversationIdRef: MutableRefObject<string | null>;
  skipLoadRef: MutableRefObject<string | null>;
  streamOwnership: StreamOwnership;
  stickToBottomRef: MutableRefObject<boolean>;
  onConversationCreated?: (id: string) => void;
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onStreamEnd?: (info: StreamEndInfo) => void;
  onInjectDeferred?: (injectId: string) => void;
  onUserInjected?: (injectId: string) => void;
};

export function useAgentStream({
  conversationId,
  webEnabled,
  docContextItems,
  primaryDocPath,
  msgs,
  setMsgs,
  setSummarized,
  setSummaryPath,
  conversationIdRef,
  skipLoadRef,
  streamOwnership,
  stickToBottomRef,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onStreamEnd,
  onInjectDeferred,
  onUserInjected,
}: UseAgentStreamOptions) {
  const { streamingRef, streamConversationIdRef, msgsConversationIdRef } =
    streamOwnership;
  const [streaming, setStreaming] = useState(false);
  const [streamViewId, setStreamViewId] = useState<string | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const [streamNowMs, setStreamNowMs] = useState(() => Date.now());
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stopRequestedRef = useRef(false);
  const onStreamEndRef = useRef(onStreamEnd);
  const onInjectDeferredRef = useRef(onInjectDeferred);
  const onUserInjectedRef = useRef(onUserInjected);
  onStreamEndRef.current = onStreamEnd;
  onInjectDeferredRef.current = onInjectDeferred;
  onUserInjectedRef.current = onUserInjected;

  useEffect(() => {
    streamingRef.current = streaming;
    if (!streaming) {
      streamingStartRef.current = null;
      streamingAssistantIdxRef.current = null;
      return;
    }
    const tick = () => {
      const now = Date.now();
      setStreamNowMs(now);
      if (streamingStartRef.current !== null) {
        setLiveElapsedMs(now - streamingStartRef.current);
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  // Conversation switch / unmount: detach observation only (do not stop the turn).
  // Important: first send creates a conversation (null → id). That must NOT abort the
  // in-flight POST /api/chat observe stream — otherwise UI freezes on an empty bubble
  // while the server turn keeps running.
  useEffect(() => {
    if (!conversationId) return;
    return () => {
      abortRef.current?.abort();
      // Release ownership immediately so the newly selected conversation can load /
      // resume without waiting for the aborted observation's finally.
      if (streamConversationIdRef.current !== null || streamingRef.current) {
        streamingRef.current = false;
        streamConversationIdRef.current = null;
        setStreaming(false);
        setStreamViewId(null);
      }
    };
  }, [conversationId, streamConversationIdRef, streamingRef]);

  function resolveDocContext(): DocContext {
    return {
      trayPaths: docContextItems.map((d) => d.path),
      docContext: docContextItems,
      primary: primaryDocPath,
    };
  }

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    conversationIdRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  async function stopStreaming() {
    stopRequestedRef.current = true;
    const cid = conversationIdRef.current;
    if (cid) {
      try {
        await stopChat(cid);
      } catch {
        /* 409 / network — still abort local observe */
      }
    }
    abortRef.current?.abort();
  }

  function patchAssistant(
    streamCid: string | null,
    updater: (msg: ChatMessage) => ChatMessage,
  ) {
    // Switched away: keep consuming until abort lands, but do not paint onto the wrong chat.
    if (streamCid && conversationIdRef.current !== streamCid) return;
    setMsgs((prev) => {
      if (prev.length === 0) return prev;
      const idx = prev.length - 1;
      const copy = [...prev];
      copy[idx] = updater(copy[idx]);
      return copy;
    });
  }

  async function consumeEvents(
    events: AsyncGenerator<ChatStreamEvent>,
    streamCid: string | null,
  ): Promise<{ streamFailed: boolean; awaitingUser: boolean }> {
    let streamFailed = false;
    let awaitingUser = false;
    let serverTimeline = false;
    for await (const { event, data } of events) {
      let userInjectId: string | undefined;
      let injectDeferredId: string | undefined;
      let kbNotify: string | null | undefined;
      let stop = false;
      patchAssistant(streamCid, (prevMsg) => {
        const result = reduceStreamEvent(
          {
            streamFailed,
            awaitingUser,
            serverTimeline,
            assistant: prevMsg,
          },
          event,
          data,
        );
        streamFailed = result.state.streamFailed;
        awaitingUser = result.state.awaitingUser;
        serverTimeline = result.state.serverTimeline;
        userInjectId = result.state.userInjectId;
        injectDeferredId = result.state.injectDeferredId;
        kbNotify = result.state.kbNotify;
        stop = result.stop;
        return result.state.assistant;
      });
      if (userInjectId) onUserInjectedRef.current?.(userInjectId);
      if (injectDeferredId) onInjectDeferredRef.current?.(injectDeferredId);
      if (kbNotify !== undefined) onKbChanged?.(kbNotify ?? undefined);
      if (streamFailed || stop) break;
    }
    return { streamFailed, awaitingUser };
  }

  function clearStreamOwnership() {
    streamingRef.current = false;
    streamConversationIdRef.current = null;
    setStreaming(false);
    setStreamViewId(null);
  }

  async function finishObservation(
    streamCid: string | null,
    info: {
      streamFailed: boolean;
      aborted: boolean;
      detached: boolean;
      awaitingUser: boolean;
    },
  ) {
    // Switch cleanup may have released ownership so another chat can resume/send.
    // A detached observation's finally must not wipe that newer claim (or its AbortController).
    const stillOwns = streamConversationIdRef.current === streamCid;
    if (stillOwns) {
      abortRef.current = null;
      stopRequestedRef.current = false;
      clearStreamOwnership();
    }
    if (skipLoadRef.current === streamCid) {
      skipLoadRef.current = null;
    }
    onSidebarRefresh?.();
    // Outbound queue is per viewed conversation — do not apply end-of-stream
    // side effects (flush/pause) when this observation is no longer the viewed chat.
    if (conversationIdRef.current === streamCid) {
      onStreamEndRef.current?.({
        failed: info.streamFailed,
        aborted: info.aborted,
        detached: info.detached,
        awaitingUser:
          !info.streamFailed &&
          !info.aborted &&
          !info.detached &&
          info.awaitingUser,
        conversationId: streamCid,
      });
    }
    const reload = shouldReloadConversation(info);
    if (!streamCid || reload === "none") return;
    getConversation(streamCid)
      .then((conv) => {
        if (conversationIdRef.current !== streamCid) return;
        if (streamingRef.current) return;
        setMsgs(
          conv.messages.map((m) =>
            normalizeLoadedMessage({
              ...m,
              injected: isInjectedUserMessage(m),
            }),
          ),
        );
        msgsConversationIdRef.current = streamCid;
        if (reload === "full") {
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
        }
      })
      .catch(() => {});
  }

  async function runAgentStream(
    apiText: string,
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    docCtx?: DocContext,
    opts?: {
      webEnabled?: boolean;
      /** 原地重新回复：复用服务端用户消息 id */
      reuseUserMessageId?: string;
      /** 替换该下标的助手气泡（不追加用户消息） */
      replaceAssistantIndex?: number;
    },
  ): Promise<boolean> {
    if (streamingRef.current) return false;
    const display = userDisplayText ?? apiText;
    const useWeb = opts?.webEnabled ?? webEnabled;
    const reuseUserMessageId = opts?.reuseUserMessageId;
    const replaceAssistantIndexOpt = opts?.replaceAssistantIndex;
    const isRetry = !!reuseUserMessageId;
    const isFirstUserQuestion =
      !isRetry && !msgs.some((m) => m.role === "user");
    stickToBottomRef.current = true;
    stopRequestedRef.current = false;
    streamingRef.current = true;
    // Claim ownership before setStreaming so the first paint scopes UI correctly.
    const priorMsgsCid = msgsConversationIdRef.current;
    streamConversationIdRef.current = conversationId;
    setStreamViewId(conversationId);
    if (conversationId) {
      msgsConversationIdRef.current = conversationId;
    }
    setStreaming(true);
    streamingStartRef.current = Date.now();
    setLiveElapsedMs(0);

    const controller = new AbortController();
    abortRef.current = controller;

    const assistantMsg: ChatMessage = {
      role: "assistant",
      ts: nowIsoDisplay(),
      timeline: [],
      sources: [],
    };
    setMsgs((m) => {
      // Never append onto another conversation's leftover bubbles after a switch.
      const sameChat =
        conversationId == null ||
        priorMsgsCid == null ||
        priorMsgsCid === conversationId;
      const base = sameChat ? m : [];
      if (isRetry && reuseUserMessageId) {
        const userIdx = base.findIndex((x) => x.id === reuseUserMessageId);
        const cut =
          userIdx >= 0
            ? userIdx + 1
            : typeof replaceAssistantIndexOpt === "number"
              ? replaceAssistantIndexOpt
              : base.length;
        const truncated = base.slice(0, Math.max(0, cut));
        streamingAssistantIdxRef.current = truncated.length;
        return [...truncated, assistantMsg];
      }
      const assistantIdx = base.length + 1;
      streamingAssistantIdxRef.current = assistantIdx;
      return [
        ...base,
        {
          role: "user",
          text: display,
          ts: nowIsoDisplay(),
          web_enabled: useWeb,
          ...(userMeta?.attachments?.length
            ? { attachments: userMeta.attachments }
            : {}),
          ...(userMeta?.doc_context?.length
            ? { doc_context: userMeta.doc_context }
            : {}),
          ...(userMeta?.primary_doc ? { primary_doc: userMeta.primary_doc } : {}),
        },
        assistantMsg,
      ];
    });

    let streamFailed = false;
    let aborted = false;
    let detached = false;
    let awaitingUser = false;
    let cid: string | null = null;
    try {
      cid = await ensureConversationId();
      streamConversationIdRef.current = cid;
      msgsConversationIdRef.current = cid;
      setStreamViewId(cid);
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const ctx = docCtx ?? resolveDocContext();
      const clientMessageId = newId();
      const result = await consumeEvents(
        chatStream(apiText, {
          conversationId: cid,
          activeDocPaths: ctx.trayPaths,
          docContext: ctx.docContext.length ? ctx.docContext : undefined,
          primaryDocPath: ctx.primary,
          webEnabled: useWeb,
          attachments: userMeta?.attachments ?? [],
          clientMessageId,
          reuseUserMessageId,
          signal: controller.signal,
        }),
        cid,
      );
      streamFailed = result.streamFailed;
      awaitingUser = result.awaitingUser;
    } catch (err) {
      if (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      ) {
        if (stopRequestedRef.current) aborted = true;
        else detached = true;
      } else {
        streamFailed = true;
        const msg = err instanceof Error ? err.message : "请求失败";
        patchAssistant(cid, (prevMsg) => ({
          ...prevMsg,
          text: `错误：${msg}`,
          status: "error",
        }));
      }
    } finally {
      await finishObservation(cid, {
        streamFailed,
        aborted,
        detached,
        awaitingUser,
      });
    }
    return true;
  }

  /** Reattach observation to a server-side running turn (e.g. after page reload). */
  async function resumeActiveTurn(
    cid: string,
    startedAt?: string | null,
  ): Promise<boolean> {
    if (streamingRef.current) return false;
    stickToBottomRef.current = true;
    stopRequestedRef.current = false;
    streamingRef.current = true;
    const priorMsgsCid = msgsConversationIdRef.current;
    streamConversationIdRef.current = cid;
    msgsConversationIdRef.current = cid;
    setStreamViewId(cid);
    setStreaming(true);
    const startedMs = startedAt ? Date.parse(startedAt) : NaN;
    streamingStartRef.current = Number.isFinite(startedMs)
      ? startedMs
      : Date.now();
    setLiveElapsedMs(Math.max(0, Date.now() - streamingStartRef.current));

    const controller = new AbortController();
    abortRef.current = controller;

    setMsgs((m) => {
      const base = priorMsgsCid === cid ? m : [];
      const last = base[base.length - 1];
      if (last?.role === "assistant") {
        streamingAssistantIdxRef.current = base.length - 1;
        return base;
      }
      streamingAssistantIdxRef.current = base.length;
      return [
        ...base,
        {
          role: "assistant",
          ts: nowIsoDisplay(),
          timeline: [],
          sources: [],
        },
      ];
    });

    let streamFailed = false;
    let aborted = false;
    let detached = false;
    let awaitingUser = false;
    try {
      const result = await consumeEvents(
        observeActiveTurnStream(cid, { signal: controller.signal }),
        cid,
      );
      streamFailed = result.streamFailed;
      awaitingUser = result.awaitingUser;
    } catch (err) {
      if (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      ) {
        if (stopRequestedRef.current) aborted = true;
        else detached = true;
      } else {
        streamFailed = true;
        const msg = err instanceof Error ? err.message : "请求失败";
        patchAssistant(cid, (prevMsg) => ({
          ...prevMsg,
          text: `错误：${msg}`,
          status: "error",
        }));
      }
    } finally {
      await finishObservation(cid, {
        streamFailed,
        aborted,
        detached,
        awaitingUser,
      });
    }
    return true;
  }

  const streamingForView = isStreamingForView(
    streaming,
    streamViewId,
    conversationId,
  );

  return {
    streaming,
    streamingForView,
    liveElapsedMs,
    streamNowMs,
    streamingAssistantIdxRef,
    streamingRef,
    runAgentStream,
    resumeActiveTurn,
    stopStreaming,
    ensureConversationId,
    resolveDocContext,
  };
}
