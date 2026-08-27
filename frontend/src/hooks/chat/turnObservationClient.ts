/**
 * 回合观测 deep module：SSE 消费、ownership、reconcile、服务端对齐。
 * React hook（useAgentStream）只做 adapter 接线。
 */

import {
  chatStream,
  createConversation,
  getActiveTurnStatus,
  getConversation,
  observeActiveTurnStream,
  stopChat,
  titleFromText,
  type ChatMessage,
  type ChatStreamEvent,
  type Conversation,
  type DocContextItem,
} from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
  timelineAwaitsUserAnswer,
} from "../../utils/chatMessage";
import { reduceStreamEvent } from "../../utils/agentStreamProjection";
import { nowIsoDisplay } from "../../utils/displayTime";
import { newId } from "../../utils/id";
import {
  buildObservationEnd,
  fetchActiveTurnStatusWithRetry,
  isActiveTurnOrphaned,
  isActiveTurnRunning,
  isActiveTurnRunningConv,
  shouldReloadConversation,
  toStreamEndPayload,
  type ObservationEndInfo,
  type ReconcileOutcome,
} from "./turnReconcile";
import {
  createStreamOwnership,
  shouldPaintStreamPatch,
  type StreamOwnership,
} from "./streamOwnership";

export type { StreamOwnership } from "./streamOwnership";
export { createStreamOwnership } from "./streamOwnership";

export type DocContext = {
  trayPaths: string[];
  docContext: DocContextItem[];
  primary: string | null;
};

export type StreamEndInfo = {
  failed: boolean;
  aborted: boolean;
  detached?: boolean;
  conversationId: string | null;
  awaitingUser?: boolean;
};

export type TurnObservationCallbacks = {
  getViewConversationId: () => string | null;
  patchMsgs: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
  setSummarized: (v: boolean) => void;
  setSummaryPath: (v: string | null) => void;
  onStreamingChange: (streaming: boolean) => void;
  onStreamViewIdChange: (id: string | null) => void;
  onReconcilingChange: (reconciling: boolean) => void;
  onStreamStartMs: (ms: number | null) => void;
  onConversationCreated?: (id: string) => void;
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onStreamEnd?: (info: StreamEndInfo) => void;
  onInjectDeferred?: (injectId: string) => void;
  onUserInjected?: (injectId: string) => void;
};

export type TurnObservationRefs = {
  getConversationIdProp: () => string | null;
  conversationIdRef: { current: string | null };
  skipLoadRef: { current: string | null };
  stickToBottomRef: { current: boolean };
  streamingAssistantIdxRef: { current: number | null };
};

const MAX_RECONCILE_PASSES = 3;

export class TurnObservationEngine {
  private abortController: AbortController | null = null;
  private stopRequested = false;
  private reconcilePasses = 0;

  constructor(
    private ownership: StreamOwnership,
    private callbacks: TurnObservationCallbacks,
    private refs: TurnObservationRefs,
  ) {}

  get streamingRef() {
    return this.ownership.streamingRef;
  }

  detachObservation(): void {
    this.abortController?.abort();
    const { streamingRef, streamConversationIdRef } = this.ownership;
    if (streamConversationIdRef.current !== null || streamingRef.current) {
      streamingRef.current = false;
      streamConversationIdRef.current = null;
      this.callbacks.onStreamingChange(false);
      this.callbacks.onStreamViewIdChange(null);
    }
  }

  async stopStreaming(): Promise<void> {
    this.stopRequested = true;
    const cid = this.refs.conversationIdRef.current;
    if (cid) {
      try {
        await stopChat(cid);
      } catch {
        /* 409 / network — still abort local observe */
      }
    }
    this.abortController?.abort();
  }

  async ensureConversationId(): Promise<string> {
    const prop = this.refs.getConversationIdProp();
    if (prop) return prop;
    const { id } = await createConversation();
    this.refs.skipLoadRef.current = id;
    this.refs.conversationIdRef.current = id;
    this.callbacks.onConversationCreated?.(id);
    return id;
  }

  async runAgentStream(
    apiText: string,
    ctx: {
      webEnabled: boolean;
      msgs: ChatMessage[];
      conversationId: string | null;
      docCtx: DocContext;
    },
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    opts?: {
      webEnabled?: boolean;
      reuseUserMessageId?: string;
      replaceAssistantIndex?: number;
    },
  ): Promise<boolean> {
    if (this.ownership.streamingRef.current) return false;

    const display = userDisplayText ?? apiText;
    const useWeb = opts?.webEnabled ?? ctx.webEnabled;
    const reuseUserMessageId = opts?.reuseUserMessageId;
    const replaceAssistantIndexOpt = opts?.replaceAssistantIndex;
    const isRetry = !!reuseUserMessageId;
    const isFirstUserQuestion =
      !isRetry && !ctx.msgs.some((m) => m.role === "user");

    this.refs.stickToBottomRef.current = true;
    this.beginObservation(ctx.conversationId);

    const assistantMsg: ChatMessage = {
      role: "assistant",
      ts: nowIsoDisplay(),
      timeline: [],
      sources: [],
    };

    const priorMsgsCid = this.ownership.msgsConversationIdRef.current;
    this.callbacks.patchMsgs((m) => {
      const sameChat =
        ctx.conversationId == null ||
        priorMsgsCid == null ||
        priorMsgsCid === ctx.conversationId;
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
        this.refs.streamingAssistantIdxRef.current = truncated.length;
        return [...truncated, assistantMsg];
      }
      this.refs.streamingAssistantIdxRef.current = base.length + 1;
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

    let serverStreamError = false;
    let aborted = false;
    let awaitingUser = false;
    let completed = false;
    let cid: string | null = null;

    try {
      cid = await this.ensureConversationId();
      this.claimStream(cid);
      if (isFirstUserQuestion) {
        this.callbacks.onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const clientMessageId = newId();
      const result = await this.consumeEvents(
        chatStream(apiText, {
          conversationId: cid,
          activeDocPaths: ctx.docCtx.trayPaths,
          docContext: ctx.docCtx.docContext.length ? ctx.docCtx.docContext : undefined,
          primaryDocPath: ctx.docCtx.primary,
          webEnabled: useWeb,
          attachments: userMeta?.attachments ?? [],
          clientMessageId,
          reuseUserMessageId,
          signal: this.abortController!.signal,
        }),
        cid,
      );
      serverStreamError = result.serverStreamError;
      awaitingUser = result.awaitingUser;
      completed = result.completed;
    } catch (err) {
      if (this.isAbortError(err) && this.stopRequested) aborted = true;
    } finally {
      await this.finishObservation(
        cid,
        buildObservationEnd({
          completed,
          serverStreamError,
          aborted,
          awaitingUser,
        }),
      );
    }
    return true;
  }

  async resumeActiveTurn(cid: string, startedAt?: string | null): Promise<boolean> {
    if (this.ownership.streamingRef.current) return false;

    this.refs.stickToBottomRef.current = true;
    this.stopRequested = false;
    this.reconcilePasses = 0;
    this.ownership.streamingRef.current = true;
    const priorMsgsCid = this.ownership.msgsConversationIdRef.current;
    this.claimStream(cid);
    this.callbacks.onStreamingChange(true);

    const startedMs = startedAt ? Date.parse(startedAt) : NaN;
    const startMs = Number.isFinite(startedMs) ? startedMs : Date.now();
    this.callbacks.onStreamStartMs(startMs);

    this.callbacks.patchMsgs((m) => {
      const base = priorMsgsCid === cid ? m : [];
      const last = base[base.length - 1];
      if (last?.role === "assistant") {
        this.refs.streamingAssistantIdxRef.current = base.length - 1;
        return base;
      }
      this.refs.streamingAssistantIdxRef.current = base.length;
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

    let serverStreamError = false;
    let aborted = false;
    let awaitingUser = false;
    let completed = false;

    try {
      const result = await this.consumeEvents(
        observeActiveTurnStream(cid, { signal: this.abortController!.signal }),
        cid,
      );
      serverStreamError = result.serverStreamError;
      awaitingUser = result.awaitingUser;
      completed = result.completed;
    } catch (err) {
      if (this.isAbortError(err) && this.stopRequested) aborted = true;
    } finally {
      await this.finishObservation(
        cid,
        buildObservationEnd({
          completed,
          serverStreamError,
          aborted,
          awaitingUser,
        }),
      );
    }
    return true;
  }

  private beginObservation(conversationId: string | null): void {
    this.stopRequested = false;
    this.reconcilePasses = 0;
    this.ownership.streamingRef.current = true;
    this.ownership.streamConversationIdRef.current = conversationId;
    this.callbacks.onStreamViewIdChange(conversationId);
    if (conversationId) {
      this.ownership.msgsConversationIdRef.current = conversationId;
    }
    this.callbacks.onStreamingChange(true);
    const now = Date.now();
    this.callbacks.onStreamStartMs(now);
    this.abortController = new AbortController();
  }

  private claimStream(cid: string): void {
    this.ownership.streamConversationIdRef.current = cid;
    this.ownership.msgsConversationIdRef.current = cid;
    this.callbacks.onStreamViewIdChange(cid);
  }

  private patchAssistant(
    streamCid: string | null,
    updater: (msg: ChatMessage) => ChatMessage,
  ): void {
    if (
      streamCid &&
      !shouldPaintStreamPatch(
        this.ownership,
        streamCid,
        this.callbacks.getViewConversationId(),
      )
    ) {
      return;
    }
    this.callbacks.patchMsgs((prev) => {
      if (prev.length === 0) return prev;
      const idx = prev.length - 1;
      const copy = [...prev];
      copy[idx] = updater(copy[idx]);
      return copy;
    });
  }

  private async consumeEvents(
    events: AsyncGenerator<ChatStreamEvent>,
    streamCid: string | null,
  ): Promise<{
    serverStreamError: boolean;
    awaitingUser: boolean;
    completed: boolean;
  }> {
    let serverStreamError = false;
    let awaitingUser = false;
    let completed = false;
    let serverTimeline = false;

    for await (const { event, data } of events) {
      let userInjectId: string | undefined;
      let injectDeferredId: string | undefined;
      let kbNotify: string | null | undefined;
      let stop = false;

      this.patchAssistant(streamCid, (prevMsg) => {
        const result = reduceStreamEvent(
          {
            streamFailed: serverStreamError,
            awaitingUser,
            serverTimeline,
            assistant: prevMsg,
          },
          event,
          data,
        );
        serverStreamError = result.state.streamFailed;
        awaitingUser = result.state.awaitingUser;
        serverTimeline = result.state.serverTimeline;
        userInjectId = result.state.userInjectId;
        injectDeferredId = result.state.injectDeferredId;
        kbNotify = result.state.kbNotify;
        stop = result.stop;
        return result.state.assistant;
      });

      if (userInjectId) this.callbacks.onUserInjected?.(userInjectId);
      if (injectDeferredId) this.callbacks.onInjectDeferred?.(injectDeferredId);
      if (kbNotify !== undefined) this.callbacks.onKbChanged?.(kbNotify ?? undefined);
      if (event === "done") completed = true;
      if (serverStreamError || stop) break;
    }

    return { serverStreamError, awaitingUser, completed };
  }

  private applyServerConversation(conv: Conversation): void {
    const activeTurnRunning = isActiveTurnRunningConv(conv);
    this.callbacks.patchMsgs(() =>
      conv.messages.map((m) =>
        normalizeLoadedMessage(
          { ...m, injected: isInjectedUserMessage(m) },
          { activeTurnRunning },
        ),
      ),
    );
    this.ownership.msgsConversationIdRef.current = conv.id;
    this.callbacks.setSummarized(!!conv.summarized);
    this.callbacks.setSummaryPath(conv.summary_path ?? null);
  }

  private awaitingUserFromConversation(conv: Conversation): boolean {
    const last = [...conv.messages].reverse().find((m) => m.role === "assistant");
    return last ? timelineAwaitsUserAnswer(last.timeline) : false;
  }

  private async reconcileWithServer(
    streamCid: string,
  ): Promise<{ outcome: ReconcileOutcome; conv?: Conversation }> {
    const turnStatus = await fetchActiveTurnStatusWithRetry(
      streamCid,
      getActiveTurnStatus,
    );
    if (!turnStatus) return { outcome: "failed" };
    if (
      !shouldPaintStreamPatch(
        this.ownership,
        streamCid,
        this.callbacks.getViewConversationId(),
      )
    ) {
      return { outcome: "settled" };
    }
    if (isActiveTurnOrphaned(turnStatus)) {
      try {
        const conv = await getConversation(streamCid);
        if (!this.ownership.streamingRef.current) {
          this.applyServerConversation(conv);
        }
        return { outcome: "failed", conv };
      } catch {
        return { outcome: "failed" };
      }
    }
    if (isActiveTurnRunning(turnStatus)) {
      const resumed = await this.resumeActiveTurn(
        streamCid,
        turnStatus.started_at,
      );
      return { outcome: resumed ? "resumed" : "failed" };
    }
    if (this.ownership.streamingRef.current) return { outcome: "settled" };
    try {
      const conv = await getConversation(streamCid);
      this.applyServerConversation(conv);
      return { outcome: "settled", conv };
    } catch {
      return { outcome: "failed" };
    }
  }

  private clearStreamOwnership(): void {
    this.ownership.streamingRef.current = false;
    this.ownership.streamConversationIdRef.current = null;
    this.callbacks.onStreamingChange(false);
    this.callbacks.onStreamViewIdChange(null);
  }

  private async finishObservation(
    streamCid: string | null,
    endInfo: ObservationEndInfo,
  ): Promise<void> {
    const stillOwns =
      this.ownership.streamConversationIdRef.current === streamCid;
    if (stillOwns) {
      this.abortController = null;
      this.stopRequested = false;
      this.clearStreamOwnership();
    }
    if (this.refs.skipLoadRef.current === streamCid) {
      this.refs.skipLoadRef.current = null;
    }
    this.callbacks.onSidebarRefresh?.();

    const canPaint =
      !!streamCid &&
      shouldPaintStreamPatch(
        this.ownership,
        streamCid,
        this.callbacks.getViewConversationId(),
      );

    const reload = shouldReloadConversation(endInfo);

    if (reload === "reconcile" && canPaint) {
      if (this.reconcilePasses >= MAX_RECONCILE_PASSES) {
        this.patchAssistant(streamCid, (prevMsg) => ({
          ...prevMsg,
          text:
            (prevMsg.text || "").trim() ||
            "错误：连接中断，无法同步服务器状态",
          status: "error",
        }));
        this.callbacks.onStreamEnd?.({
          ...toStreamEndPayload(endInfo, { reconcileFailed: true }),
          conversationId: streamCid,
        });
        return;
      }
      this.reconcilePasses += 1;
      this.callbacks.onReconcilingChange(true);
      try {
        const { outcome, conv } = await this.reconcileWithServer(streamCid!);
        if (outcome === "resumed") {
          this.reconcilePasses = 0;
          return;
        }
        if (outcome === "settled" && conv) {
          if (
            shouldPaintStreamPatch(
              this.ownership,
              streamCid,
              this.callbacks.getViewConversationId(),
            )
          ) {
            this.callbacks.onStreamEnd?.({
              failed: false,
              aborted: false,
              detached: false,
              awaitingUser: this.awaitingUserFromConversation(conv),
              conversationId: streamCid,
            });
          }
          return;
        }
        this.patchAssistant(streamCid, (prevMsg) => ({
          ...prevMsg,
          text:
            (prevMsg.text || "").trim() ||
            "错误：连接中断，无法同步服务器状态",
          status: "error",
        }));
        if (canPaint) {
          this.callbacks.onStreamEnd?.({
            ...toStreamEndPayload(endInfo, { reconcileFailed: true }),
            conversationId: streamCid,
          });
        }
      } finally {
        this.callbacks.onReconcilingChange(false);
      }
      return;
    }

    if (canPaint) {
      this.callbacks.onStreamEnd?.({
        ...toStreamEndPayload(endInfo),
        conversationId: streamCid,
      });
    }

    if (!streamCid || reload === "none" || reload === "reconcile") return;

    getConversation(streamCid)
      .then((conv) => {
        if (
          !shouldPaintStreamPatch(
            this.ownership,
            streamCid,
            this.callbacks.getViewConversationId(),
          )
        ) {
          return;
        }
        if (this.ownership.streamingRef.current) return;
        this.applyServerConversation(conv);
      })
      .catch(() => {});
  }

  private isAbortError(err: unknown): boolean {
    return (
      (err instanceof DOMException && err.name === "AbortError") ||
      (err instanceof Error && err.name === "AbortError")
    );
  }
}
