import { useEffect, useRef, useState } from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import { useConversationMemoryEvents } from "../hooks/chat/useConversationMemoryEvents";
import type { JumpTarget } from "../hooks/chat/useConversationJump";
import {
  uploadFile,
  summarizeConversation,
  type DocContextItem,
  type IngestResult,
  type SourceRef,
} from "../api";
import { useDocPreview } from "../contexts/DocPreviewContext";
import { markToolBlockResolved } from "../utils/chatMessage";
import { nowIsoDisplay } from "../utils/displayTime";
import { ChatMessageList } from "./chat/ChatMessageList";
import { ComposerTray } from "./ComposerTray";
import { ComposerToolbar } from "./ComposerToolbar";
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
  });
  const stickToBottomRef = useRef(true);
  const {
    streaming,
    liveElapsedMs,
    streamingAssistantIdxRef,
    runAgentStream,
    resolveDocContext,
  } = useAgentStream({
    conversationId,
    previewPath,
    webEnabled,
    docPaths: documentPaths,
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
  });
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
    if (!input.trim() || streaming) return;
    const text = input;
    setInput("");

    const filesToUpload = [...pendingFiles];
    const uploadedPaths: string[] = [];

    if (filesToUpload.length > 0) {
      setPendingFiles([]);
      try {
        for (const pf of filesToUpload) {
          const r = await uploadFile(pf.file, "未分类");
          uploadedPaths.push(r.attachment);
          refreshKb(r.attachment);
        }
      } catch (err) {
        setPendingFiles(filesToUpload);
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
      void runAgentStream(result.continue_prompt, choiceLabel);
      return;
    }
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
        streamingAssistantIdxRef={streamingAssistantIdxRef}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={handleOpenSource}
        onQuestionResolved={handleQuestionResolved}
      />
      <div className="chat-composer-wrap">
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
                placeholder="输入消息…"
                disabled={streaming}
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
