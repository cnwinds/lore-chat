import {
  computeCumulative,
  formatDuration,
  getMessageCopyText,
  normalizeDocContext,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
} from "../../api";
import { DocChip, FileChip } from "../ComposerTray";
import { formatMessageTs, isInjectedUserMessage } from "../../utils/chatMessage";
import { MarkdownContent } from "../MarkdownContent";
import { KbAttachmentList } from "../KbAttachmentList";
import { ChatSources } from "../ChatSources";
import { CopyButton } from "../CopyButton";
import { TimelineBlockView } from "../TimelineBlockView";
import { MessageRangeHighlight } from "./MessageRangeHighlight";
import { useEffect, useRef, useState } from "react";
import {
  collectTimelineTextSpans,
  isHighlightOffsetVersion,
  mapGlobalRangeToTimelineHighlights,
} from "../../utils/unicodeHighlight";
import type { HighlightRangeDetail } from "../../hooks/chat/useConversationJump";
import type { ConversationLinkTarget } from "../../utils/conversationLinks";

export type ChatMessageRowProps = {
  message: ChatMessage;
  isLiveStreaming: boolean;
  liveElapsedMs: number;
  /** 流式墙钟，供单工具 started_at_ms 秒表 */
  streamNowMs?: number;
  previewPath?: string | null;
  conversationId: string | null;
  onOpenSource: (src: SourceRef) => void;
  onOpenConversation?: (target: ConversationLinkTarget) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};

function basename(path: string): string {
  return path.split("/").pop() || path;
}

/** 时间线 generate_image 已展示的路径，消息脚不再重复。 */
function timelineGenerateImagePaths(m: ChatMessage): Set<string> {
  const out = new Set<string>();
  const add = (paths: string[] | undefined) => {
    for (const p of paths ?? []) {
      if (p) out.add(p);
    }
  };
  for (const block of m.timeline ?? []) {
    if (block.type === "tool" && block.tool === "generate_image") {
      add(block.attachments);
    } else if (block.type === "parallel") {
      for (const child of block.children) {
        if (child.type === "tool" && child.tool === "generate_image") {
          add(child.attachments);
        }
      }
    }
  }
  return out;
}

/** 消息脚附件：去掉已在生图工具块展示的路径。 */
function footAttachmentPaths(m: ChatMessage): string[] {
  const attachments = m.attachments ?? [];
  if (!attachments.length || m.role === "user") return [];
  const shown = timelineGenerateImagePaths(m);
  return attachments.filter((p) => !shown.has(p));
}

function renderUserMessageChips(m: ChatMessage) {
  const docItems = normalizeDocContext(m.doc_context);
  const hasDocs = docItems.length > 0;
  const hasFiles = (m.attachments?.length ?? 0) > 0;
  if (!hasDocs && !hasFiles) return null;

  return (
    <div className="chat-user-chips">
      {docItems.map((item) => (
        <DocChip
          key={`${item.kind}:${item.path}`}
          title={
            item.kind === "skill_root"
              ? `Skill · ${basename(item.path) || "根"}`
              : basename(item.path)
          }
          tooltip={item.path}
          primary={item.kind === "document" && item.path === m.primary_doc}
          skill={item.kind === "skill_root"}
        />
      ))}
      {m.attachments?.map((a) => (
        <FileChip key={a} name={basename(a)} tooltip={a} />
      ))}
    </div>
  );
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

function renderMessageMeta(
  m: ChatMessage,
  isLive: boolean,
  liveElapsedMs: number,
) {
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
  if (
    !timeStr &&
    (durationMs === undefined || durationMs <= 0) &&
    !copyText &&
    !m.model_name
  ) {
    return null;
  }

  return (
    <div className="chat-meta chat-meta-assistant">
      <div className="chat-meta-info">
        {m.model_name && (
          <span title={m.model_failover ? "已切换至备胎模型" : undefined}>
            {m.model_name}
            {m.model_failover ? " · 已切换" : ""}
          </span>
        )}
        {timeStr && <span>{timeStr}</span>}
        {!isLive && durationMs !== undefined && durationMs > 0 && (
          <span>用时 {formatDuration(durationMs)}</span>
        )}
      </div>
      {copyText && !isLive && <CopyButton text={copyText} />}
    </div>
  );
}

function renderMessageContent(
  m: ChatMessage,
  isLive: boolean,
  liveElapsedMs: number,
  streamNowMs: number | undefined,
  previewPath: string | null | undefined,
  conversationId: string | null,
  onOpenSource: (src: SourceRef) => void,
  onOpenConversation: ((target: ConversationLinkTarget) => void) | undefined,
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void,
  highlightRange: { start: number; end: number } | null,
) {
  if (m.timeline && m.timeline.length > 0) {
    const cumulative = computeCumulative(m.timeline);
    const textSpans = collectTimelineTextSpans(m.timeline);
    const shouldMapOntoTimeline =
      !highlightRange || textSpans.length > 0;
    if (shouldMapOntoTimeline) {
      const blockHighlights =
        highlightRange && textSpans.length > 0
          ? mapGlobalRangeToTimelineHighlights(
              m.timeline,
              highlightRange.start,
              highlightRange.end,
            )
          : null;
      return m.timeline
        .map((block, originalIndex) => ({ block, originalIndex }))
        .filter(({ block }) => block.type !== "user_inject")
        .map(({ block, originalIndex }) => (
        <TimelineBlockView
          key={
            block.type === "tool"
              ? block.id
              : block.type === "parallel"
                ? block.batch_id
                : block.type === "think"
                  ? `think-${originalIndex}`
                  : `text-${originalIndex}`
          }
          block={block}
          cumulative={cumulative}
          liveElapsedMs={isLive ? liveElapsedMs : undefined}
          nowMs={isLive ? streamNowMs : undefined}
          isLive={isLive}
          onOpenSource={onOpenSource}
          onOpenConversation={onOpenConversation}
          previewPath={previewPath}
          conversationId={conversationId}
          onQuestionResolved={onQuestionResolved}
          textHighlight={blockHighlights?.get(originalIndex)}
        />
      ));
    }
  }
  if (m.text) {
    if (m.role === "user") {
      if (highlightRange) {
        return (
          <div className="chat-user-text">
            <MessageRangeHighlight
              text={m.text}
              start={highlightRange.start}
              end={highlightRange.end}
            />
          </div>
        );
      }
      return <div className="chat-user-text">{m.text}</div>;
    }
    return (
      <MarkdownContent
        className="markdown-body chat-markdown"
        onOpenConversation={onOpenConversation}
        highlightRange={highlightRange}
      >
        {m.text}
      </MarkdownContent>
    );
  }
  return null;
}

export function messageHasBody(m: ChatMessage, isLive: boolean): boolean {
  if (m.role === "user") return true;
  if (m.timeline?.length) return true;
  if (m.text) return true;
  if (m.sources?.length) return true;
  if (m.attachments?.length) return true;
  if (normalizeDocContext(m.doc_context).length) return true;
  if (isLive) return false;
  return !!(m.ts || getMessageDuration(m) || getMessageCopyText(m));
}

export function ChatMessageRow({
  message: m,
  isLiveStreaming,
  liveElapsedMs,
  streamNowMs,
  previewPath,
  conversationId,
  onOpenSource,
  onOpenConversation,
  onQuestionResolved,
}: ChatMessageRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [highlightRange, setHighlightRange] = useState<{
    start: number;
    end: number;
  } | null>(null);

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;
    const onHighlight = (ev: Event) => {
      const detail = (ev as CustomEvent<HighlightRangeDetail>).detail;
      if (!detail) return;
      if (!isHighlightOffsetVersion(detail.offsetVersion)) return;
      setHighlightRange({ start: detail.start, end: detail.end });
      window.setTimeout(() => setHighlightRange(null), 3000);
    };
    el.addEventListener("highlight-range", onHighlight);
    return () => el.removeEventListener("highlight-range", onHighlight);
  }, []);

  const footPaths = footAttachmentPaths(m);

  return (
    <div
      ref={rowRef}
      className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}
      {...(m.id ? { "data-message-id": m.id } : {})}
    >
      <div className={`chat-bubble chat-bubble-${m.role}`}>
        {m.role === "assistant" && m.model_failover ? (
          <div className="chat-failover-banner" role="status">
            高优先级模型暂不可用，已切换至 {m.model_name || "备胎模型"}
          </div>
        ) : null}
        {m.role === "user" && isInjectedUserMessage(m) && (
            <div className="chat-inject-tag">已插入本轮</div>
          )}
        {m.role === "assistant" && m.status === "interrupted" && !isLiveStreaming && (
          <div className="chat-interrupted-note" role="status">
            本轮因刷新或断线中断；未完成的步骤已标出，可继续发消息或回答待确认项。
          </div>
        )}
        {m.role === "user" && renderUserMessageChips(m)}
        {renderMessageContent(
          m,
          isLiveStreaming,
          liveElapsedMs,
          streamNowMs,
          previewPath,
          conversationId,
          onOpenSource,
          onOpenConversation,
          onQuestionResolved,
          highlightRange,
        )}
        {m.sources && m.sources.length > 0 && (
          <ChatSources
            sources={m.sources}
            previewPath={previewPath}
            onOpen={onOpenSource}
          />
        )}
        {footPaths.length > 0 ? (
          <KbAttachmentList
            paths={footPaths}
            className="kb-attachment-list"
            imageClassName="chat-gen-image"
            linkClassName="chat-gen-image-link"
          />
        ) : null}
        {renderMessageMeta(m, isLiveStreaming, liveElapsedMs)}
      </div>
    </div>
  );
}
