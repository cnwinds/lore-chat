import { useCallback, useEffect, useRef, useState } from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import { useConversationMemoryEvents } from "../hooks/chat/useConversationMemoryEvents";
import { useSendQueue } from "../hooks/chat/useSendQueue";
import {
  applyInjectDeferred,
  applyStreamEnd,
  applyUserInjected,
} from "../hooks/chat/outboundQueue";
import type { JumpTarget } from "../hooks/chat/useConversationJump";
import {
  chatInject,
  kbImport,
  summarizeConversation,
  type DocContextItem,
  type IngestResult,
  type SourceRef,
} from "../api";
import { useDocPreview } from "../contexts/DocPreviewContext";
import { markToolBlockResolved } from "../utils/chatMessage";
import { nowIsoDisplay } from "../utils/displayTime";
import {
  mergeGroupText,
  takeNextGroup,
  SEND_QUEUE_MAX,
  type SendQueueItem,
} from "../utils/sendQueue";
import { ChatMessageList } from "./chat/ChatMessageList";
import { ComposerTray } from "./ComposerTray";
import { ComposerToolbar } from "./ComposerToolbar";
import { ComposerSendQueue } from "./ComposerSendQueue";
import { ArchiveConversationModal } from "./ArchiveConversationModal";
import type { DocTrayItem, PendingFile } from "../types/composer";
import { suggestArchivePath } from "../utils/suggestArchivePath";

type ComposerDocItem = DocTrayItem;

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

type Props = {
  conversationId: string | null;
  onConversationCreated?: (id: string) => void;
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onOpenSource?: (src: SourceRef) => void;
  onJumpToConversation?: (target: JumpTarget) => void;
  pendingJump?: JumpTarget | null;
  onJumpHandled?: () => void;
  docTrayItems?: ComposerDocItem[];
  primaryDocPath?: string | null;
  documentPaths?: string[];
  docContextItems?: DocContextItem[];
  onTraySetPrimary?: (path: string) => void;
  onTrayRemove?: (path: string) => void;
};

export function Chat({
  conversationId,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onOpenSource,
  onJumpToConversation,
  pendingJump = null,
  onJumpHandled,
  docTrayItems = [],
  primaryDocPath = null,
  documentPaths = [],
  docContextItems = [],
  onTraySetPrimary,
  onTrayRemove,
}: Props) {
  const { previewPath, openDoc, refreshKb } = useDocPreview();

  const [input, setInput] = useState("");
  const [archiving, setArchiving] = useState(false);
  const [archiveModalOpen, setArchiveModalOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [webEnabled, setWebEnabled] = useState<boolean>(
    () => localStorage.getItem("lorechat.webSearch") === "1",
  );
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const skipLoadRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const conversationIdRef = useRef(conversationId);
  const stickToBottomRef = useRef(true);
  const resumeActiveTurnRef = useRef<
    (cid: string, startedAt?: string | null) => Promise<boolean>
  >(async () => false);

  const {
    msgs,
    setMsgs,
    loadingHistory,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
  } = useChatConversation({
    conversationId,
    skipLoadRef,
    streamingRef,
    pendingJump,
    onJumpHandled,
    onActiveTurn: (cid, startedAt) => {
      void resumeActiveTurnRef.current(cid, startedAt);
    },
  });

  const sendQueue = useSendQueue(conversationId);
  const itemsRef = useRef(sendQueue.items);
  const pausedRef = useRef(sendQueue.paused);
  const flushingRef = useRef(false);
  const pendingGroupRef = useRef<SendQueueItem[] | null>(null);
  itemsRef.current = sendQueue.items;
  pausedRef.current = sendQueue.paused;

  const flushQueueRef = useRef<() => Promise<void>>(async () => {});
  const maybeInjectFrontRef = useRef<() => Promise<void>>(async () => {});

  const handleStreamEnd = useCallback(
    (info: {
      failed: boolean;
      aborted: boolean;
      detached?: boolean;
      awaitingUser?: boolean;
    }) => {
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

  const {
    streaming,
    liveElapsedMs,
    streamNowMs,
    streamingAssistantIdxRef,
    runAgentStream,
    resumeActiveTurn,
    stopStreaming,
    ensureConversationId,
    resolveDocContext,
  } = useAgentStream({
    conversationId,
    previewPath,
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
    onKbChanged: refreshKb,
    onStreamEnd: handleStreamEnd,
    onInjectDeferred: handleInjectDeferred,
    onUserInjected: handleUserInjected,
  });
  resumeActiveTurnRef.current = resumeActiveTurn;
  const { messagesContainerRef } = useChatScroll(
    [msgs, loadingHistory, streaming],
    stickToBottomRef,
  );
  const { notice: memoryNotice, dismissNotice: dismissMemoryNotice } =
    useConversationMemoryEvents(conversationId);

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(
      Math.max(el.scrollHeight, INPUT_MIN_HEIGHT),
      INPUT_MAX_HEIGHT,
    );
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }, [input]);

  function toggleWebSearch() {
    setWebEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("lorechat.webSearch", next ? "1" : "0");
      return next;
    });
  }

  const runOutbound = useCallback(
    async (group: SendQueueItem[]) => {
      const text = mergeGroupText(group);
      const first = group[0];
      const docContext = first.doc_context ?? [];
      const documentPathsForRun = docContext
        .filter((d) => d.kind !== "skill_root")
        .map((d) => d.path);
      return runAgentStream(
        text,
        text,
        {
          attachments: first.attachments?.length ? first.attachments : undefined,
          doc_context: docContext.length ? docContext : undefined,
          primary_doc: first.primary_doc ?? undefined,
        },
        {
          documentPaths: documentPathsForRun,
          docContext,
          primary: first.primary_doc ?? null,
        },
        { webEnabled: first.webEnabled },
      );
    },
    [runAgentStream],
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
  }, [runOutbound, sendQueue]);

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
    const locked = [
      ...group.map((g) => ({ ...g, locked: true })),
      ...rest,
    ];
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
  }, [sendQueue]);

  maybeInjectFrontRef.current = maybeInjectFront;

  useEffect(() => {
    if (streaming) {
      void maybeInjectFrontRef.current();
    }
  }, [streaming, sendQueue.items]);

  async function send() {
    if (!input.trim() && pendingFiles.length === 0) return;
    const text = input.trim();
    if (!text && pendingFiles.length === 0) return;

    const filesToUpload = [...pendingFiles];
    const uploadedPaths: string[] = [];

    setInput("");
    if (filesToUpload.length > 0) {
      setPendingFiles([]);
      try {
        for (const pf of filesToUpload) {
          const r = await kbImport(pf.file, "未分类");
          uploadedPaths.push(r.rel_path);
          refreshKb(r.rel_path);
        }
      } catch (err) {
        setPendingFiles(filesToUpload);
        setInput(text);
        const msg = err instanceof Error ? err.message : "上传失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
        ]);
        return;
      }
    }

    const ctx = resolveDocContext();
    if (
      ctx.docContext.length === 0 &&
      /[（(]*(几|两|\d+).*文档|合并|整合/.test(text)
    ) {
      setInput(text);
      window.alert(
        "请先在侧栏用 Ctrl+单击 将文档加入输入框上方的托盘，再发送。",
      );
      return;
    }

    const shouldQueue = streaming || sendQueue.items.length > 0;
    if (!shouldQueue) {
      await runAgentStream(
        text,
        text,
        {
          attachments: uploadedPaths.length ? uploadedPaths : undefined,
          doc_context: ctx.docContext.length ? ctx.docContext : undefined,
          primary_doc: ctx.primary ?? undefined,
        },
        ctx,
      );
      return;
    }

    if (!conversationId) {
      try {
        await ensureConversationId();
      } catch (err) {
        setInput(text);
        const msg = err instanceof Error ? err.message : "创建对话失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
        ]);
        return;
      }
    }

    const newItem: SendQueueItem = {
      id: crypto.randomUUID(),
      text,
      timing: "defer",
      mergeWithNext: false,
      doc_context: ctx.docContext.length ? ctx.docContext : undefined,
      primary_doc: ctx.primary,
      attachments: uploadedPaths.length ? uploadedPaths : undefined,
      webEnabled,
      locked: false,
      error: null,
    };
    if (itemsRef.current.length >= SEND_QUEUE_MAX) {
      window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
      setInput(text);
      return;
    }
    sendQueue.setItems([...itemsRef.current, newItem]);
    itemsRef.current = [...itemsRef.current, newItem];

    if (!streaming && !sendQueue.paused) {
      void flushQueue();
    } else if (streaming) {
      void maybeInjectFront();
    }
  }

  function handleStop() {
    stopStreaming();
    sendQueue.setPaused(true);
  }

  function handleContinue() {
    sendQueue.setPaused(false);
    sendQueue.setItems(
      itemsRef.current.map((x) => ({ ...x, error: null, locked: false })),
    );
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }

  function handleRetry() {
    sendQueue.setItems(
      itemsRef.current.map((x) => ({ ...x, error: null })),
    );
    sendQueue.setPaused(false);
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }

  function handleSkipFailed() {
    const items = itemsRef.current;
    const next = items[0]?.error ? items.slice(1) : items.filter((x) => !x.error);
    sendQueue.setItems(next);
    sendQueue.setPaused(false);
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
  }

  function openArchiveModal() {
    if (!conversationId || streaming || archiving) return;
    if (!msgs.some((m) => m.role === "user")) return;
    setArchiveModalOpen(true);
  }

  async function performArchive(directory: string, filename: string) {
    if (!conversationId || streaming || archiving) return;
    const targetCid = conversationId;
    setArchiving(true);
    try {
      const result = await summarizeConversation(targetCid, { directory, filename });
      setArchiveModalOpen(false);
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        if (result.rel_path) refreshKb(result.rel_path);
        return;
      }
      const text =
        result.status === "saved" && result.rel_path
          ? `已把本次会话归档为文档：${result.rel_path}`
          : result.message || "归档完成";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text, ts: nowIsoDisplay() },
      ]);
      if (result.rel_path) {
        setSummarized(true);
        setSummaryPath(result.rel_path);
        refreshKb(result.rel_path);
        openDoc(result.rel_path, undefined, { pin: true });
      }
      onSidebarRefresh?.();
    } catch (err) {
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        return;
      }
      const msg = err instanceof Error ? err.message : "归档失败";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
      ]);
    } finally {
      setArchiving(false);
    }
  }

  const firstUserText =
    msgs.find((m) => m.role === "user")?.text?.trim() ?? "";
  const archiveDefaults = suggestArchivePath(summaryPath, firstUserText);

  function handleQuestionResolved(
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) {
    setMsgs((prev) => markToolBlockResolved(prev, blockId, choiceLabel));
    refreshKb(result.rel_path ?? undefined);

    if (result.status === "continue" && result.continue_prompt) {
      // Answering unpauses; the follow-up stream will auto-flush on done
      // unless it asks another question.
      sendQueue.setPaused(false);
      pausedRef.current = false;
      if (streaming || sendQueue.items.length > 0) {
        sendQueue.enqueue({
          text: result.continue_prompt,
          timing: "defer",
          webEnabled,
        });
        if (!streaming) void flushQueue();
      } else {
        void runAgentStream(result.continue_prompt, choiceLabel);
      }
      return;
    }
    // Resume deferred queue after the user answered.
    sendQueue.setPaused(false);
    pausedRef.current = false;
    queueMicrotask(() => {
      void flushQueueRef.current();
    });
    if (result.status === "saved" && result.message) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: nowIsoDisplay(),
        },
      ]);
      if (result.rel_path) {
        openDoc(result.rel_path, undefined, { pin: true });
      }
      return;
    }
    if (result.status === "acknowledged") {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: nowIsoDisplay(),
        },
      ]);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const id = `${Date.now()}-${f.name}`;
    setPendingFiles((prev) => [
      ...prev,
      { id, file: f, name: f.name, size: f.size },
    ]);
    e.target.value = "";
  }

  function removePendingFile(id: string) {
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void send();
    }
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "conversation" && src.message_id) {
      onJumpToConversation?.({
        conversationId: src.cid,
        messageId: src.message_id,
        startChar: src.start_char,
        endChar: src.end_char,
        offsetVersion: src.offset_version,
      });
      return;
    }
    if (src.type === "kb" && src.path) {
      openDoc(src.path, src.excerpt, { pin: true });
      return;
    }
    if (onOpenSource) {
      onOpenSource(src);
    } else if (src.type === "web" || src.type === "search") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <div className="chat-panel">
      {memoryNotice && (
        <div className="chat-memory-notice" role="status">
          <span>{memoryNotice.label}</span>
          <button
            type="button"
            className="chat-memory-notice-dismiss"
            onClick={dismissMemoryNotice}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
      )}
      <ChatMessageList
        msgs={msgs}
        loadingHistory={loadingHistory}
        streaming={streaming}
        liveElapsedMs={liveElapsedMs}
        streamNowMs={streamNowMs}
        streamingAssistantIdxRef={streamingAssistantIdxRef}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={handleOpenSource}
        onQuestionResolved={handleQuestionResolved}
      />
      <div className="chat-composer-wrap">
        <ComposerSendQueue
          items={sendQueue.items}
          paused={sendQueue.paused}
          onContinue={handleContinue}
          onRetry={handleRetry}
          onSkipFailed={handleSkipFailed}
          onUpdateText={(id, text) => sendQueue.updateItem(id, { text })}
          onSetTiming={sendQueue.setItemTiming}
          onToggleMerge={(id) => {
            const item = sendQueue.items.find((x) => x.id === id);
            if (!item) return;
            const idx = sendQueue.items.findIndex((x) => x.id === id);
            const nextItem = sendQueue.items[idx + 1];
            const merge = !item.mergeWithNext;
            if (merge && nextItem && nextItem.timing !== item.timing) {
              sendQueue.setItemTiming(nextItem.id, item.timing);
            }
            sendQueue.updateItem(id, { mergeWithNext: merge });
          }}
          onRemove={sendQueue.removeItem}
          onMove={sendQueue.moveItem}
          onSetAllTiming={sendQueue.setAllTiming}
          onSetAllMerge={sendQueue.setAllMerge}
          onClear={sendQueue.clear}
        />
        <div className="composer-card">
          <ComposerTray
            items={docTrayItems}
            primaryPath={primaryDocPath}
            pendingFiles={pendingFiles}
            onSetPrimary={onTraySetPrimary ?? (() => {})}
            onRemoveDoc={onTrayRemove ?? (() => {})}
            onRemoveFile={removePendingFile}
          />
          <div className="composer-body">
            <div className="composer-input">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onInputKeyDown}
                rows={1}
                placeholder={streaming ? "输入消息加入队列…" : "输入消息…"}
                title="Ctrl+Enter 发送"
                style={{
                  minHeight: INPUT_MIN_HEIGHT,
                  maxHeight: INPUT_MAX_HEIGHT,
                }}
              />
            </div>
            <ComposerToolbar
              webEnabled={webEnabled}
              onToggleWeb={toggleWebSearch}
              streaming={streaming}
              canSend={!!input.trim() || pendingFiles.length > 0}
              archiving={archiving}
              conversationId={conversationId}
              summarized={summarized}
              summaryPath={summaryPath}
              canArchive={msgs.some((m) => m.role === "user")}
              onArchive={openArchiveModal}
              onOpenSummary={(path) => openDoc(path, undefined, { pin: true })}
              onAttachClick={() => fileInputRef.current?.click()}
              onSend={send}
              onStop={handleStop}
              fileInputRef={fileInputRef}
              onFileChange={onFile}
            />
          </div>
        </div>
      </div>
      <ArchiveConversationModal
        open={archiveModalOpen}
        initialDirectory={archiveDefaults.directory}
        initialFilename={archiveDefaults.filename}
        submitting={archiving}
        onClose={() => !archiving && setArchiveModalOpen(false)}
        onConfirm={(directory, filename) => void performArchive(directory, filename)}
      />
    </div>
  );
}
