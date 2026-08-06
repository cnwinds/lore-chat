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
  updateTimeline,
  KB_MUTATING_TOOLS,
  type ChatMessage,
  type ChatStreamEvent,
  type DocContextItem,
  type SourceRef,
} from "../../api";
import {
  isInjectedUserMessage,
  kbPathFromToolResult,
  normalizeLoadedMessage,
  timelineAwaitsUserAnswer,
} from "../../utils/chatMessage";
import { nowIsoDisplay } from "../../utils/displayTime";

export type DocContext = {
  documentPaths: string[];
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
  documentPaths: string[];
  docContextItems: DocContextItem[];
  primaryDocPath: string | null;
  msgs: ChatMessage[];
  setMsgs: Dispatch<SetStateAction<ChatMessage[]>>;
  setSummarized: Dispatch<SetStateAction<boolean>>;
  setSummaryPath: Dispatch<SetStateAction<string | null>>;
  conversationIdRef: MutableRefObject<string | null>;
  skipLoadRef: MutableRefObject<string | null>;
  streamingRef: MutableRefObject<boolean>;
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
  previewPath: _previewPath,
  webEnabled,
  documentPaths,
  docContextItems,
  primaryDocPath,
  msgs,
  setMsgs,
  setSummarized,
  setSummaryPath,
  conversationIdRef,
  skipLoadRef,
  streamingRef,
  stickToBottomRef,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onStreamEnd,
  onInjectDeferred,
  onUserInjected,
}: UseAgentStreamOptions) {
  const [streaming, setStreaming] = useState(false);
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
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [conversationId]);

  function resolveDocContext(): DocContext {
    return {
      documentPaths,
      docContext: docContextItems,
      primary: primaryDocPath,
    };
  }

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
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

  function patchAssistant(updater: (msg: ChatMessage) => ChatMessage) {
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
  ): Promise<{ streamFailed: boolean; awaitingUser: boolean }> {
    let streamFailed = false;
    let awaitingUser = false;
    for await (const { event, data } of events) {
      if (event === "error") {
        const message = (data.message as string) || "请求失败";
        patchAssistant((msg) => ({ ...msg, text: `错误：${message}` }));
        streamFailed = true;
        break;
      }

      if (event === "user_inject") {
        const injectId = data.inject_id as string;
        patchAssistant((prevMsg) => ({
          ...prevMsg,
          timeline: updateTimeline(prevMsg.timeline ?? [], event, data),
        }));
        onUserInjectedRef.current?.(injectId);
        continue;
      }

      if (event === "inject_deferred") {
        onInjectDeferredRef.current?.(data.inject_id as string);
        continue;
      }

      patchAssistant((prevMsg) => {
        const msg = { ...prevMsg };
        if (event !== "done") {
          msg.timeline = updateTimeline(msg.timeline ?? [], event, data);
        }
        if (event === "done") {
          msg.sources = (data.sources as SourceRef[]) || [];
          if (data.total_duration_ms !== undefined) {
            msg.total_duration_ms = data.total_duration_ms as number;
          }
          msg.ts = nowIsoDisplay();
          awaitingUser = timelineAwaitsUserAnswer(msg.timeline);
        }
        return msg;
      });

      if (event === "tool_result") {
        if (
          (KB_MUTATING_TOOLS as readonly string[]).includes(data.tool as string)
        ) {
          onKbChanged?.(kbPathFromToolResult(data));
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
    }
    return { streamFailed, awaitingUser };
  }

  async function finishObservation(
    cid: string | null,
    info: {
      streamFailed: boolean;
      aborted: boolean;
      detached: boolean;
      awaitingUser: boolean;
    },
  ) {
    abortRef.current = null;
    stopRequestedRef.current = false;
    streamingRef.current = false;
    setStreaming(false);
    skipLoadRef.current = null;
    onSidebarRefresh?.();
    const endCid = conversationIdRef.current ?? cid;
    onStreamEndRef.current?.({
      failed: info.streamFailed,
      aborted: info.aborted,
      detached: info.detached,
      awaitingUser:
        !info.streamFailed && !info.aborted && !info.detached && info.awaitingUser,
      conversationId: endCid,
    });
    if (endCid && !info.streamFailed && !info.aborted && !info.detached) {
      getConversation(endCid)
        .then((conv) => {
          if (conversationIdRef.current !== endCid) return;
          if (streamingRef.current) return;
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
        })
        .catch(() => {});
    } else if (endCid && info.aborted) {
      getConversation(endCid)
        .then((conv) => {
          if (conversationIdRef.current !== endCid) return;
          if (streamingRef.current) return;
          setMsgs(
            conv.messages.map((m) =>
              normalizeLoadedMessage({
                ...m,
                injected: isInjectedUserMessage(m),
              }),
            ),
          );
        })
        .catch(() => {});
    }
  }

  async function runAgentStream(
    apiText: string,
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    docCtx?: DocContext,
    opts?: { webEnabled?: boolean },
  ): Promise<boolean> {
    if (streamingRef.current) return false;
    const display = userDisplayText ?? apiText;
    const isFirstUserQuestion = !msgs.some((m) => m.role === "user");
    stickToBottomRef.current = true;
    stopRequestedRef.current = false;
    streamingRef.current = true;
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
      const assistantIdx = m.length + 1;
      streamingAssistantIdxRef.current = assistantIdx;
      return [
        ...m,
        {
          role: "user",
          text: display,
          ts: nowIsoDisplay(),
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
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const ctx = docCtx ?? resolveDocContext();
      const clientMessageId = crypto.randomUUID();
      const useWeb = opts?.webEnabled ?? webEnabled;
      const result = await consumeEvents(
        chatStream(apiText, {
          conversationId: cid,
          activeDocPaths: ctx.documentPaths,
          docContext: ctx.docContext.length ? ctx.docContext : undefined,
          primaryDocPath: ctx.primary,
          webEnabled: useWeb,
          attachments: userMeta?.attachments ?? [],
          clientMessageId,
          signal: controller.signal,
        }),
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
        patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
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
    setStreaming(true);
    const startedMs = startedAt ? Date.parse(startedAt) : NaN;
    streamingStartRef.current = Number.isFinite(startedMs)
      ? startedMs
      : Date.now();
    setLiveElapsedMs(Math.max(0, Date.now() - streamingStartRef.current));

    const controller = new AbortController();
    abortRef.current = controller;

    setMsgs((m) => {
      const last = m[m.length - 1];
      if (last?.role === "assistant") {
        streamingAssistantIdxRef.current = m.length - 1;
        return m;
      }
      streamingAssistantIdxRef.current = m.length;
      return [
        ...m,
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
        patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
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

  return {
    streaming,
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
