import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  chatStream,
  computeCumulative,
  formatDuration,
  getMessageCopyText,
  updateTimeline,
  uploadFile,
  downloadUrl,
  createConversation,
  getConversation,
  summarizeConversation,
  titleFromText,
  KB_MUTATING_TOOLS,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
  type TimelineBlock,
} from "../api";
import { MarkdownContent } from "./MarkdownContent";
import { ChatSources } from "./ChatSources";
import { CopyButton } from "./CopyButton";
import { TimelineBlockView } from "./TimelineBlockView";
import { ComposerTray } from "./ComposerTray";
import { ComposerToolbar } from "./ComposerToolbar";
import type { PendingFile } from "../types/composer";

type ComposerDocItem = { path: string; title: string };

type Props = {
  conversationId: string | null;
  previewPath?: string | null;
  onConversationCreated?: (id: string) => void;
  /** 发出该会话第一条用户问题时，用问题摘要更新侧边栏标题 */
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onKbChanged?: (changedPath?: string) => void;
  onOpenSource?: (src: SourceRef) => void;
  onOpenDoc?: (path: string, excerpt?: string) => void;
  docTrayItems?: ComposerDocItem[];
  primaryDocPath?: string | null;
  docPaths?: string[];
  onTraySetPrimary?: (path: string) => void;
  onTrayRemove?: (path: string) => void;
};

function kbPathFromToolResult(data: Record<string, unknown>): string | undefined {
  const sources = data.sources as SourceRef[] | undefined;
  const kb = sources?.find((s) => s.type === "kb");
  return kb?.path;
}

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;
const SCROLL_BOTTOM_THRESHOLD = 80;

function isNearBottom(container: HTMLElement): boolean {
  const distance =
    container.scrollHeight - container.scrollTop - container.clientHeight;
  return distance <= SCROLL_BOTTOM_THRESHOLD;
}

function basename(path: string): string {
  return path.split("/").pop() || path;
}

function renderUserMessageChips(m: ChatMessage) {
  const hasDocs = (m.doc_context?.length ?? 0) > 0;
  const hasFiles = (m.attachments?.length ?? 0) > 0;
  if (!hasDocs && !hasFiles) return null;

  return (
    <div className="chat-user-chips">
      {m.doc_context?.map((path) => (
        <span
          key={path}
          className={`chat-user-doc-chip${path === m.primary_doc ? " chat-user-doc-chip--primary" : ""}`}
          title={path}
        >
          {path === m.primary_doc && (
            <span className="chat-user-doc-chip-bar" aria-hidden />
          )}
          <span className="chat-user-doc-chip-title">{basename(path)}</span>
        </span>
      ))}
      {m.attachments?.map((path) => (
        <a
          key={path}
          className="chat-user-file-chip"
          href={downloadUrl(path)}
          title={path}
        >
          <span className="chat-user-file-icon" aria-hidden>
            📄
          </span>
          <span className="chat-user-file-name">{basename(path)}</span>
        </a>
      ))}
    </div>
  );
}

function formatMessageTs(ts: string): string {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

function markToolBlockResolved(
  messages: ChatMessage[],
  blockId: string,
  choiceLabel: string,
): ChatMessage[] {
  function patchBlock(block: TimelineBlock): TimelineBlock {
    if (block.type === "tool" && block.id === blockId) {
      return { ...block, choice_resolved: choiceLabel };
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: block.children.map(patchBlock),
      };
    }
    return block;
  }
  return messages.map((msg) =>
    msg.timeline
      ? { ...msg, timeline: msg.timeline.map(patchBlock) }
      : msg,
  );
}

export function Chat({
  conversationId,
  previewPath,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onKbChanged,
  onOpenSource,
  onOpenDoc,
  docTrayItems = [],
  primaryDocPath = null,
  docPaths = [],
  onTraySetPrimary = () => {},
  onTrayRemove = () => {},
}: Props) {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [summarized, setSummarized] = useState(false);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  const [liveElapsedMs, setLiveElapsedMs] = useState(0);
  const [webEnabled, setWebEnabled] = useState<boolean>(
    () => localStorage.getItem("lorechat.webSearch") === "1",
  );
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const streamingStartRef = useRef<number | null>(null);
  const streamingAssistantIdxRef = useRef<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  /** 本地刚创建的对话 ID，流式结束前跳过从服务端拉历史（避免 StrictMode 双次 effect 覆盖流式状态） */
  const skipLoadRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const conversationIdRef = useRef(conversationId);

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  function scrollMessagesToBottom() {
    const el = messagesContainerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }

  function adjustInputHeight() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight, INPUT_MIN_HEIGHT), INPUT_MAX_HEIGHT);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }

  useEffect(() => {
    adjustInputHeight();
  }, [input]);

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
        if (!cancelled) {
          setMsgs(conv.messages);
          setSummarized(!!conv.summarized);
          setSummaryPath(conv.summary_path ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
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
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      stickToBottomRef.current = isNearBottom(el);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useLayoutEffect(() => {
    if (stickToBottomRef.current) {
      scrollMessagesToBottom();
    }
  }, [msgs, loadingHistory, streaming]);

  useEffect(() => {
    streamingRef.current = streaming;
    if (!streaming) {
      streamingStartRef.current = null;
      streamingAssistantIdxRef.current = null;
      return;
    }
    const tick = () => {
      if (streamingStartRef.current !== null) {
        setLiveElapsedMs(Date.now() - streamingStartRef.current);
      }
    };
    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
  }, [streaming]);

  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;
    const { id } = await createConversation();
    skipLoadRef.current = id;
    onConversationCreated?.(id);
    return id;
  }

  function toggleWebSearch() {
    setWebEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("lorechat.webSearch", next ? "1" : "0");
      return next;
    });
  }

  /** 托盘优先；托盘为空时回退到当前右侧预览文档 */
  function resolveDocContext(): { paths: string[]; primary: string | null } {
    if (docPaths.length > 0) {
      return { paths: docPaths, primary: primaryDocPath };
    }
    if (previewPath) {
      return { paths: [previewPath], primary: previewPath };
    }
    return { paths: [], primary: null };
  }

  async function runAgentStream(
    apiText: string,
    userDisplayText?: string,
    userMeta?: Pick<ChatMessage, "attachments" | "doc_context" | "primary_doc">,
    docCtx?: { paths: string[]; primary: string | null },
  ) {
    if (streaming) return;
    const display = userDisplayText ?? apiText;
    const isFirstUserQuestion = !msgs.some((m) => m.role === "user");
    stickToBottomRef.current = true;
    setStreaming(true);
    streamingRef.current = true;
    streamingStartRef.current = Date.now();
    setLiveElapsedMs(0);

    const assistantMsg: ChatMessage = {
      role: "assistant",
      ts: new Date().toISOString(),
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
          ts: new Date().toISOString(),
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
    // 流式期间助手消息始终是数组的最后一项；直接定位它，
    // 避免依赖 setMsgs 更新器里异步写入的 ref（在“继续”流程下会读到过期值，
    // 导致把 timeline 写进了 msgs[0] 这条用户消息，输出错位到右上角）。
    const patchAssistant = (updater: (msg: ChatMessage) => ChatMessage) =>
      setMsgs((prev) => {
        if (prev.length === 0) return prev;
        const idx = prev.length - 1;
        const copy = [...prev];
        copy[idx] = updater(copy[idx]);
        return copy;
      });

    try {
      const cid = await ensureConversationId();
      if (isFirstUserQuestion) {
        onFirstQuestionTitle?.(cid, titleFromText(display));
      }
      const ctx = docCtx ?? resolveDocContext();
      for await (const { event, data } of chatStream(apiText, {
        conversationId: cid,
        activeDocPaths: ctx.paths,
        primaryDocPath: ctx.primary,
        webEnabled,
        attachments: userMeta?.attachments ?? [],
      })) {
        if (event === "error") {
          const message = (data.message as string) || "请求失败";
          patchAssistant((msg) => ({ ...msg, text: `错误：${message}` }));
          break;
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
            msg.ts = new Date().toISOString();
          }
          return msg;
        });

        if (event === "tool_result") {
          if ((KB_MUTATING_TOOLS as readonly string[]).includes(data.tool as string)) {
            onKbChanged?.(kbPathFromToolResult(data));
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "请求失败";
      patchAssistant((prevMsg) => ({ ...prevMsg, text: `错误：${msg}` }));
    } finally {
      streamingRef.current = false;
      setStreaming(false);
      skipLoadRef.current = null;
      // 流关闭后服务端才完成 append_exchange（含标题），此时再刷新侧边栏
      onSidebarRefresh?.();
      const cid = conversationIdRef.current;
      if (cid) {
        getConversation(cid)
          .then((conv) => {
            if (conversationIdRef.current !== cid) return;
            setSummarized(!!conv.summarized);
            setSummaryPath(conv.summary_path ?? null);
          })
          .catch(() => {});
      }
    }
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
          onKbChanged?.(r.attachment);
        }
      } catch (err) {
        setPendingFiles(filesToUpload);
        const msg = err instanceof Error ? err.message : "上传失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: new Date().toISOString() },
        ]);
        return;
      }
    }

    const ctx = resolveDocContext();
    if (
      ctx.paths.length === 0 &&
      /这.*(几|两|\d+).*文档|合并|整合/.test(text)
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
        doc_context: ctx.paths.length ? ctx.paths : undefined,
        primary_doc: ctx.primary ?? undefined,
      },
      ctx,
    );
  }

  async function archiveConversation() {
    if (!conversationId || streaming || archiving) return;
    if (!msgs.some((m) => m.role === "user")) return;
    const targetCid = conversationId;
    setArchiving(true);
    try {
      const result = await summarizeConversation(targetCid);
      // 沉淀耗时较长，用户可能已切到其他会话；只把结果写回发起沉淀的那条会话
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        if (result.rel_path) onKbChanged?.(result.rel_path);
        return;
      }
      const text =
        result.status === "saved" && result.rel_path
          ? `已把本次会话归档为文档：${result.rel_path}`
          : result.message || "归档完成";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text, ts: new Date().toISOString() },
      ]);
      if (result.rel_path) {
        setSummarized(true);
        setSummaryPath(result.rel_path);
        onKbChanged?.(result.rel_path);
        onOpenDoc?.(result.rel_path);
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
        { role: "assistant", text: `错误：${msg}`, ts: new Date().toISOString() },
      ]);
    } finally {
      setArchiving(false);
    }
  }

  function handleQuestionResolved(
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) {
    setMsgs((prev) => markToolBlockResolved(prev, blockId, choiceLabel));
    onKbChanged?.(result.rel_path ?? undefined);

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
          ts: new Date().toISOString(),
        },
      ]);
      if (result.rel_path) {
        onOpenDoc?.(result.rel_path);
      }
      return;
    }
    if (result.status === "acknowledged") {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: new Date().toISOString(),
        },
      ]);
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : String(Date.now());
    setPendingFiles((prev) => [
      ...prev,
      { id, file: f, name: f.name, size: f.size },
    ]);
    e.target.value = "";
  }

  function removePendingFile(id: string) {
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  }

  function onAttachClick() {
    fileInputRef.current?.click();
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      send();
    }
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "conversation") {
      // 未归档会话来源仅作展示，暂不跳转
      return;
    }
    if (src.type === "kb" && src.path) {
      if (onOpenDoc) {
        onOpenDoc(src.path, src.excerpt);
      } else {
        onOpenSource?.(src);
      }
      return;
    }
    if (onOpenSource) {
      onOpenSource(src);
    } else if (src.type === "web" || src.type === "search") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  function getMessageDuration(m: ChatMessage): number | undefined {
    if (m.total_duration_ms !== undefined) return m.total_duration_ms;
    if (!m.timeline?.length) return undefined;
    const { toolCumulative, parallelCumulative } = computeCumulative(m.timeline);
    let max = 0;
    for (const v of toolCumulative.values()) max = Math.max(max, v);
    for (const v of parallelCumulative.values()) max = Math.max(max, v);
    return max > 0 ? max : undefined;
  }

  function renderMessageMeta(m: ChatMessage, isLive: boolean) {
    const copyText = getMessageCopyText(m);

    if (m.role === "user") {
      if (!copyText && !m.ts) return null;
      return (
        <div className="chat-meta chat-meta-user">
          {copyText && <CopyButton text={copyText} />}
          <span className="chat-meta-spacer" />
          {m.ts && <span>{formatMessageTs(m.ts)}</span>}
        </div>
      );
    }

    const durationMs = isLive ? liveElapsedMs : getMessageDuration(m);
    const timeStr = !isLive && m.ts ? formatMessageTs(m.ts) : null;
    if (!timeStr && (durationMs === undefined || durationMs <= 0) && !copyText) {
      return null;
    }

    return (
      <div className="chat-meta chat-meta-assistant">
        <div className="chat-meta-info">
          {timeStr && <span>{timeStr}</span>}
          {!isLive && durationMs !== undefined && durationMs > 0 && (
            <span>用时 {formatDuration(durationMs)}</span>
          )}
        </div>
        {copyText && !isLive && <CopyButton text={copyText} />}
      </div>
    );
  }

  function renderMessageContent(m: ChatMessage, isLive: boolean) {
    if (m.timeline && m.timeline.length > 0) {
      const cumulative = computeCumulative(m.timeline);
      return m.timeline.map((block, i) => (
        <TimelineBlockView
          key={
            block.type === "tool"
              ? block.id
              : block.type === "parallel"
                ? block.batch_id
                : `text-${i}`
          }
          block={block}
          cumulative={cumulative}
          liveElapsedMs={isLive ? liveElapsedMs : undefined}
          onOpenSource={handleOpenSource}
          previewPath={previewPath}
          conversationId={conversationId}
          onQuestionResolved={handleQuestionResolved}
        />
      ));
    }
    if (m.text) {
      if (m.role === "user") {
        return (
          <>
            {renderUserMessageChips(m)}
            <div className="chat-user-text">{m.text}</div>
          </>
        );
      }
      return (
        <MarkdownContent className="markdown-body chat-markdown">
          {m.text}
        </MarkdownContent>
      );
    }
    if (m.role === "user") {
      return renderUserMessageChips(m);
    }
    return null;
  }

  function messageHasBody(m: ChatMessage, isLive: boolean): boolean {
    if (m.role === "user") return true;
    if (m.timeline?.length) return true;
    if (m.text) return true;
    if (m.sources?.length) return true;
    if (m.attachments?.length) return true;
    if (m.doc_context?.length) return true;
    if (isLive) return false;
    return !!(m.ts || getMessageDuration(m) || getMessageCopyText(m));
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages" ref={messagesContainerRef}>
        <div className="chat-messages-inner">
        {loadingHistory && <div className="chat-empty">加载对话中…</div>}
        {!loadingHistory && msgs.length === 0 && (
          <div className="chat-empty">
            直接输入即可。Agent 会自动检索知识库、搜索网页并整理到知识库。
          </div>
        )}
        {msgs.map((m, i) => {
          const isLiveStreaming =
            streaming && streamingAssistantIdxRef.current === i;
          if (!messageHasBody(m, isLiveStreaming)) {
            return null;
          }
          return (
          <div
            key={`${m.ts ?? "msg"}-${i}`}
            className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}
          >
            <div className={`chat-bubble chat-bubble-${m.role}`}>
              {renderMessageContent(m, isLiveStreaming)}
              {m.sources && m.sources.length > 0 && (
                <ChatSources
                  sources={m.sources}
                  previewPath={previewPath}
                  onOpen={handleOpenSource}
                />
              )}
              {m.role !== "user" &&
                m.attachments?.map((a) => (
                  <div key={a}>
                    <a href={downloadUrl(a)}>下载附件：{basename(a)}</a>
                  </div>
                ))}
              {renderMessageMeta(m, isLiveStreaming)}
            </div>
          </div>
          );
        })}
        <div ref={messagesEndRef} className="chat-messages-anchor" aria-hidden />
        </div>
      </div>
      {streaming && (
        <div className="chat-streaming-wrap">
          <div className="chat-streaming-bar">
            <span className="chat-streaming-label">思考中…</span>
            {liveElapsedMs > 0 && (
              <span className="chat-streaming-duration">
                用时 {formatDuration(liveElapsedMs)}
              </span>
            )}
          </div>
        </div>
      )}
      <div className="chat-composer-wrap">
      <div className="composer-card">
        <ComposerTray
          items={docTrayItems}
          primaryPath={primaryDocPath}
          pendingFiles={pendingFiles}
          onSetPrimary={onTraySetPrimary}
          onRemoveDoc={onTrayRemove}
          onRemoveFile={removePendingFile}
        />
        <div className="composer-input">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onInputKeyDown}
            rows={1}
            placeholder="输入问题或记录内容…（Ctrl+Enter 发送）"
            disabled={streaming}
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
          archiving={archiving}
          conversationId={conversationId}
          summarized={summarized}
          summaryPath={summaryPath}
          canArchive={msgs.some((m) => m.role === "user")}
          onArchive={archiveConversation}
          onOpenSummary={onOpenDoc}
          onAttachClick={onAttachClick}
          onSend={send}
          fileInputRef={fileInputRef}
          onFileChange={onFileChange}
        />
      </div>
      </div>
    </div>
  );
}

