import { useCallback, useEffect, useRef, useState } from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import { useConversationMemoryEvents } from "../hooks/chat/useConversationMemoryEvents";
import { useSendQueue } from "../hooks/chat/useSendQueue";
import { useOutboundOrchestrator } from "../hooks/chat/useOutboundOrchestrator";
import type { JumpTarget } from "../hooks/chat/useConversationJump";
import {
  normalizeDocContext,
  summarizeConversation,
  type DocContextItem,
  type IngestResult,
  type SourceRef,
} from "../api";
import { useDocPreview } from "../contexts/DocPreviewContext";
import { markToolBlockResolved } from "../utils/chatMessage";
import { nowIsoDisplay } from "../utils/displayTime";
import { newId } from "../utils/id";
import {
  mergeGroupText,
  SEND_QUEUE_MAX,
  type SendQueueItem,
} from "../utils/sendQueue";
import { ChatMessageList } from "./chat/ChatMessageList";
import { ComposerTray } from "./ComposerTray";
import { ComposerToolbar } from "./ComposerToolbar";
import { ComposerSendQueue } from "./ComposerSendQueue";
import { ArchiveConversationModal } from "./ArchiveConversationModal";
import type { DocTrayItem, PendingFile } from "../types/composer";
import { extractClipboardImageFiles } from "../utils/clipboard";
import { importChatAttachment } from "../utils/chatAttachmentImport";
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

  const streamEndRef = useRef<(info: {
    failed: boolean;
    aborted: boolean;
    detached?: boolean;
    awaitingUser?: boolean;
  }) => void>(() => {});
  const injectDeferredRef = useRef<(id: string) => void>(() => {});
  const userInjectedRef = useRef<(id: string) => void>(() => {});

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
    onStreamEnd: (info) => streamEndRef.current(info),
    onInjectDeferred: (id) => injectDeferredRef.current(id),
    onUserInjected: (id) => userInjectedRef.current(id),
  });
  resumeActiveTurnRef.current = resumeActiveTurn;

  const runOutbound = useCallback(
    async (group: SendQueueItem[]) => {
      const text = mergeGroupText(group);
      const first = group[0];
      const docContext = normalizeDocContext(first.doc_context);
      const trayPaths = docContext.map((d) => d.path);
      return runAgentStream(
        text,
        text,
        {
          attachments: first.attachments?.length ? first.attachments : undefined,
          doc_context: docContext.length ? docContext : undefined,
          primary_doc: first.primary_doc ?? undefined,
        },
        {
          trayPaths,
          docContext,
          primary: first.primary_doc ?? null,
        },
        { webEnabled: first.webEnabled },
      );
    },
    [runAgentStream],
  );

  const outbound = useOutboundOrchestrator({
    sendQueue,
    streaming,
    streamingRef,
    conversationIdRef,
    runOutbound,
  });
  streamEndRef.current = outbound.handleStreamEnd;
  injectDeferredRef.current = outbound.handleInjectDeferred;
  userInjectedRef.current = outbound.handleUserInjected;

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
          const rel = await importChatAttachment(pf.file);
          uploadedPaths.push(rel);
          refreshKb(rel);
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
        "请先在侧栏用 Ctrl+单击 将文件或目录加入工作托盘（顶层「技能」除外），再发送。",
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
      id: newId(),
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
    if (outbound.itemsRef.current.length >= SEND_QUEUE_MAX) {
      window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
      setInput(text);
      return;
    }
    outbound.enqueueAndKick(newItem);
  }

  function handleStop() {
    stopStreaming();
    outbound.handleStop();
  }

  function handleContinue() {
    outbound.handleContinue();
  }

  function handleRetry() {
    outbound.handleRetry();
  }

  function handleSkipFailed() {
    outbound.handleSkipFailed();
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
      outbound.pausedRef.current = false;
      sendQueue.setPaused(false);
      if (streaming || sendQueue.items.length > 0) {
        sendQueue.enqueue({
          text: result.continue_prompt,
          timing: "defer",
          webEnabled,
        });
        if (!streaming) void outbound.flushQueue();
      } else {
        void runAgentStream(result.continue_prompt, choiceLabel);
      }
      return;
    }
    // Resume deferred queue after the user answered.
    outbound.unpauseAndFlush();
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

  function addPendingFiles(files: File[]) {
    if (!files.length) return;
    setPendingFiles((prev) => [
      ...prev,
      ...files.map((f) => ({
        id: `${Date.now()}-${f.name}-${newId()}`,
        file: f,
        name: f.name,
        size: f.size,
      })),
    ]);
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    addPendingFiles([f]);
    e.target.value = "";
  }

  function removePendingFile(id: string) {
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  }

  function onInputPaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const images = extractClipboardImageFiles(e.clipboardData);
    if (!images.length) return;
    e.preventDefault();
    addPendingFiles(images);
    const pasteText = e.clipboardData.getData("text/plain");
    if (!pasteText) return;
    const el = e.currentTarget;
    const start = el.selectionStart ?? input.length;
    const end = el.selectionEnd ?? input.length;
    setInput(input.slice(0, start) + pasteText + input.slice(end));
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void send();
    }
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "conversation") {
      onJumpToConversation?.({
        conversationId: src.cid,
        ...(src.message_id ? { messageId: src.message_id } : {}),
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

  function handleOpenConversation(target: {
    conversationId: string;
    messageId?: string;
  }) {
    onJumpToConversation?.({
      conversationId: target.conversationId,
      ...(target.messageId ? { messageId: target.messageId } : {}),
    });
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
        onOpenConversation={handleOpenConversation}
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
                onPaste={onInputPaste}
                rows={1}
                placeholder={streaming ? "输入消息加入队列…" : "输入消息…"}
                title="Ctrl+Enter 发送；可粘贴图片到托盘"
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
