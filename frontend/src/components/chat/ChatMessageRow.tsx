import {
  computeCumulative,
  formatDuration,
  formatMessageTokens,
  getMessageCopyText,
  isMarkdownPath,
  normalizeDocContext,
  type ChatMessage,
  type IngestResult,
  type RoleSummary,
  type SourceRef,
} from "../../api";
import { RoleAvatar } from "../role/RoleAvatar";
import { resolveGroupSpeaker } from "../../utils/groupChatDisplay";
import { DocChip } from "../ComposerTray";
import { formatMessageTs, isInjectedUserMessage, canRetryAssistantReply } from "../../utils/chatMessage";
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
import { stripProtocolMarkup } from "../../utils/visibleText";

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
  /** 失败/中断时重新发起本轮用户提问 */
  onRetryReply?: () => void;
  retryDisabled?: boolean;
  readOnly?: boolean;
  /** 群现场按说话人画；一对一仍用默认气泡 */
  layout?: "dm" | "group";
  roles?: RoleSummary[];
  respondingRoleId?: string | null;
};

function basename(path: string): string {
  return path.split("/").pop() || path;
}

/** 时间线工具块已展示的附件路径，消息脚（参考文档下方）不再重复。 */
function timelineToolAttachmentPaths(m: ChatMessage): Set<string> {
  const out = new Set<string>();
  const add = (paths: string[] | undefined) => {
    for (const p of paths ?? []) {
      if (p) out.add(p);
    }
  };
  for (const block of m.timeline ?? []) {
    if (block.type === "tool") {
      add(block.attachments);
    } else if (block.type === "parallel") {
      for (const child of block.children) {
        if (child.type === "tool") add(child.attachments);
      }
    }
  }
  return out;
}

/** 消息脚附件：去掉已在工具块展示的路径。 */
function footAttachmentPaths(m: ChatMessage): string[] {
  const attachments = m.attachments ?? [];
  if (!attachments.length || m.role === "user") return [];
  const shown = timelineToolAttachmentPaths(m);
  return attachments.filter((p) => !shown.has(p));
}

function UserMessageChips({ m }: { m: ChatMessage }) {
  const docItems = normalizeDocContext(m.doc_context);
  const attachments = m.attachments ?? [];
  const hasDocs = docItems.length > 0;
  const hasFiles = attachments.length > 0;
  if (!hasDocs && !hasFiles) return null;

  return (
    <div className="chat-user-chips">
      {docItems.map((item) => (
        <DocChip
          key={item.path}
          title={basename(item.path)}
          tooltip={item.path}
          primary={
            typeof m.primary_doc === "string" &&
            isMarkdownPath(m.primary_doc) &&
            item.path === m.primary_doc
          }
        />
      ))}
      {hasFiles ? (
        <KbAttachmentList
          paths={attachments}
          className="chat-user-attachment-list"
          thumbClassName="composer-image-chip chat-user-image-chip"
        />
      ) : null}
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
  onRetryReply?: () => void,
  retryDisabled?: boolean,
) {
  const copyText = getMessageCopyText(m);
  const showRetry =
    !isLive && !!onRetryReply && canRetryAssistantReply(m);

  if (m.role === "user") {
    if (!copyText && !m.ts) return null;
    return (
      <div className="chat-meta chat-meta-user">
        {copyText && <CopyButton text={copyText} />}
        {m.ts && <span>{formatMessageTs(m.ts)}</span>}
      </div>
    );
  }

  const durationMs = isLive ? liveElapsedMs : getMessageDuration(m);
  const timeStr = !isLive && m.ts ? formatMessageTs(m.ts) : null;
  const showDuration = durationMs !== undefined && durationMs > 0;
  const tokenLine = formatMessageTokens(m);
  if (!timeStr && !showDuration && !copyText && !m.model_name && !showRetry && !tokenLine) {
    return null;
  }

  return (
    <>
      <div className="chat-meta chat-meta-assistant">
        {(timeStr || showDuration) && (
          <span className="chat-meta-when">
            {timeStr ? <span className="chat-meta-clock">{timeStr}</span> : null}
            {showDuration && durationMs != null ? (
              <span className="chat-meta-elapsed">
                {timeStr
                  ? `（${formatDuration(durationMs)}）`
                  : formatDuration(durationMs)}
              </span>
            ) : null}
          </span>
        )}
        {m.model_name ? (
          <span
            className="chat-meta-model"
            title={m.model_failover ? "已切换至备胎模型" : m.model_name}
          >
            {m.model_name}
            {m.model_failover ? " 已切换" : ""}
          </span>
        ) : null}
        {showRetry || (copyText && !isLive) ? (
          <span className="chat-meta-actions">
            {showRetry ? (
              <button
                type="button"
                className="chat-retry-btn"
                onClick={onRetryReply}
                disabled={retryDisabled}
                title="重新生成这一轮回复（不重复提问）"
              >
                重新回复
              </button>
            ) : null}
            {copyText && !isLive ? <CopyButton text={copyText} /> : null}
          </span>
        ) : null}
      </div>
      {tokenLine ? <div className="chat-meta-tokens">{tokenLine}</div> : null}
    </>
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
    const text = stripProtocolMarkup(m.text);
    if (!text) return null;
    return (
      <MarkdownContent
        className="markdown-body chat-markdown"
        onOpenConversation={onOpenConversation}
        highlightRange={highlightRange}
      >
        {text}
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
  onRetryReply,
  retryDisabled,
  readOnly = false,
  layout = "dm",
  roles = [],
  respondingRoleId = null,
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
  const timelineImagePaths = [...timelineToolAttachmentPaths(m)];
  const showRetry =
    !readOnly && !isLiveStreaming && !!onRetryReply && canRetryAssistantReply(m);
  const groupSpeaker =
    layout === "group"
      ? resolveGroupSpeaker(m, roles, respondingRoleId)
      : null;
  const groupRowKind =
    groupSpeaker?.kind === "owner"
      ? "owner"
      : groupSpeaker?.kind === "system"
        ? "system"
        : "role";
  const rowClass =
    layout === "group"
      ? `chat-row chat-row-group chat-row-group-${groupRowKind}`
      : `chat-row ${
          m.speaker_kind === "role" && m.role === "user"
            ? "chat-row-peer"
            : m.role === "user"
              ? "chat-row-user"
              : "chat-row-assistant"
        }`;
  const bubbleClass =
    layout === "group"
      ? `chat-bubble ${
          groupSpeaker?.kind === "owner"
            ? "chat-bubble-user"
            : groupSpeaker?.kind === "system"
              ? "chat-bubble-system"
              : "chat-bubble-assistant"
        }`
      : `chat-bubble ${
          m.speaker_kind === "role" && m.role === "user"
            ? "chat-bubble-peer"
            : `chat-bubble-${m.role}`
        }`;

  const bubble = (
      <div className={bubbleClass}>
        {m.role === "assistant" && m.model_failover ? (
          <div className="chat-failover-banner" role="status">
            高优先级模型暂不可用，已切换至 {m.model_name || "备胎模型"}
          </div>
        ) : null}
        {layout !== "group" && m.role === "user" && m.speaker_kind === "role" && (
          <div className="chat-peer-tag">
            来自 {m.speaker_name || "其他角色"}
          </div>
        )}
        {m.role === "user" &&
          groupSpeaker?.kind !== "system" &&
          isInjectedUserMessage(m) && (
            <div className="chat-inject-tag">已插入本轮</div>
          )}
        {m.role === "assistant" && m.status === "interrupted" && !isLiveStreaming && (
          <div className="chat-interrupted-note" role="status">
            本轮因刷新或断线中断；未完成的步骤已标出，可继续发消息、回答待确认项，或重新回复。
          </div>
        )}
        {m.role === "user" && groupSpeaker?.kind !== "system" && (
          <UserMessageChips m={m} />
        )}
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
            hideImagePaths={timelineImagePaths}
          />
        )}
        {footPaths.length > 0 ? (
          <KbAttachmentList
            paths={footPaths}
            className="kb-attachment-list"
            imageClassName="chat-gen-image"
            thumbClassName="chat-gen-image-link"
          />
        ) : null}
        {renderMessageMeta(
          m,
          isLiveStreaming,
          liveElapsedMs,
          showRetry ? onRetryReply : undefined,
          retryDisabled,
        )}
      </div>
  );

  return (
    <div
      ref={rowRef}
      className={rowClass}
      {...(m.id ? { "data-message-id": m.id } : {})}
      data-speaker-kind={groupSpeaker?.kind || m.speaker_kind || m.role}
      data-speaker-id={groupSpeaker?.id || m.speaker_id || undefined}
    >
      {layout === "group" && groupSpeaker?.kind === "role" ? (
        <div className="chat-row-group-col">
          <div className="chat-row-group-head">
            <RoleAvatar
              name={groupSpeaker.name}
              seed={groupSpeaker.id || groupSpeaker.name}
              avatar={groupSpeaker.role?.avatar}
              size={20}
              className="chat-row-group-avatar"
            />
            <div className="chat-row-group-name">{groupSpeaker.name}</div>
          </div>
          {bubble}
        </div>
      ) : (
        bubble
      )}
    </div>
  );
}
